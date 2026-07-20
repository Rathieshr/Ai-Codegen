from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.document_ingestion import DocumentIngestionService, build_document_ingestion_router
from backend.document_ingestion.service import DocumentParsingFailed, DocumentValidationError
from backend.platform.shared import JsonMapStore
from backend.requirement_intake import RequirementIngestionService


ROOT = Path(__file__).resolve().parents[1]


class DocumentUploadParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = DocumentIngestionService(self.root / "documents")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def upload(self, name: str, content: bytes, media_type: str = "") -> dict:
        return self.service.upload({
            "fileName": name,
            "mediaType": media_type,
            "contentBase64": base64.b64encode(content).decode(),
            "projectId": "gridhub",
            "actor": "Product Owner",
        })

    def test_txt_is_stored_parsed_and_detected_as_brd(self):
        uploaded = self.upload("device-health.txt", b"Business Requirements Document\nBusiness Objective: improve device health visibility.")
        self.assertEqual("Uploaded", uploaded["status"])
        self.assertFalse(uploaded["readyForAnalysis"])
        self.assertNotIn("originalStorageKey", uploaded)
        parsed = self.service.parse(uploaded["documentId"])
        self.assertEqual("Ready", parsed["status"])
        self.assertEqual("BRD", parsed["parsed"]["detectedType"])
        self.assertEqual("en", parsed["parsed"]["language"])
        self.assertGreaterEqual(parsed["parsed"]["pages"], 1)
        self.assertTrue(parsed["readyForAnalysis"])

    def test_markdown_extracts_title_sections_and_metadata(self):
        content = b"# Device Health PRD\n\nProduct Requirements Document\n\n## Goals\nShow offline devices.\n\n## Users\nOperations users."
        parsed = self.service.parse(self.upload("device-health.md", content, "text/markdown")["documentId"])
        self.assertEqual("Device Health PRD", parsed["parsed"]["title"])
        self.assertEqual("PRD", parsed["parsed"]["detectedType"])
        self.assertEqual(["Device Health PRD", "Goals", "Users"], [item["title"] for item in parsed["parsed"]["sections"]])
        self.assertEqual("utf8", parsed["parsed"]["metadata"]["parser"])

    def test_docx_extracts_openxml_title_sections_pages_and_metadata(self):
        uploaded = self.upload(
            "alarm-center.docx",
            _docx_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        parsed = self.service.parse(uploaded["documentId"])
        self.assertEqual("Alarm Center SRS", parsed["parsed"]["title"])
        self.assertEqual("SRS", parsed["parsed"]["detectedType"])
        self.assertEqual(4, parsed["parsed"]["pages"])
        self.assertEqual("HEI Team", parsed["parsed"]["metadata"]["author"])
        self.assertIn("System Requirements", [item["title"] for item in parsed["parsed"]["sections"]])

    def test_pdf_extracts_pages_title_and_text(self):
        uploaded = self.upload("functional-spec.pdf", _pdf_bytes(), "application/pdf")
        parsed = self.service.parse(uploaded["documentId"])
        self.assertEqual("Ready", parsed["status"])
        self.assertEqual(1, parsed["parsed"]["pages"])
        self.assertEqual("Functional Specification", parsed["parsed"]["detectedType"])
        self.assertIn("Functional Specification", parsed["parsed"]["text"])

    def test_corrupted_pdf_preserves_original_and_failure_log(self):
        uploaded = self.upload("corrupted.pdf", b"%PDF-1.7\nnot a complete document", "application/pdf")
        with self.assertRaises(DocumentParsingFailed):
            self.service.parse(uploaded["documentId"])
        failed = self.service.get(uploaded["documentId"])
        self.assertEqual("Failed", failed["status"])
        self.assertIn("corrupted", failed["error"].lower())
        self.assertEqual("ParseFailed", failed["extractionLog"][-1]["stage"])
        stored = next((self.root / "documents/originals").iterdir())
        self.assertTrue(stored.exists())

    def test_large_text_document_is_bounded_and_page_estimate_is_available(self):
        content = ("Software Requirements Specification\nThe system shall retain device health history.\n" * 30000).encode()
        parsed = self.service.parse(self.upload("large-srs.txt", content)["documentId"])
        self.assertEqual("SRS", parsed["parsed"]["detectedType"])
        self.assertGreater(parsed["parsed"]["pages"], 100)
        self.assertEqual(len(content), parsed["sizeBytes"])

    def test_unknown_document_format_is_rejected(self):
        with self.assertRaisesRegex(DocumentValidationError, "Unsupported document format"):
            self.upload("requirements.xlsx", b"not supported")

    def test_api_upload_get_and_parse_contract(self):
        app = FastAPI()
        app.include_router(build_document_ingestion_router(self.service))
        client = TestClient(app)
        response = client.post("/documents/upload", json={
            "fileName": "requirements.md",
            "mediaType": "text/markdown",
            "contentBase64": base64.b64encode(b"# PRD\nProduct Requirements Document").decode(),
            "projectId": "gridhub",
        })
        self.assertEqual(200, response.status_code)
        document_id = response.json()["documentId"]
        parsed = client.post(f"/documents/{document_id}/parse", json={})
        self.assertEqual(200, parsed.status_code)
        loaded = client.get(f"/documents/{document_id}")
        self.assertEqual("Ready", loaded.json()["status"])
        self.assertEqual("PRD", loaded.json()["parsed"]["detectedType"])

    def test_parsed_document_becomes_normalized_requirement_document(self):
        parsed = self.service.parse(self.upload(
            "device-health.md",
            b"# Device Health PRD\nProduct Requirements Document\n## Goal\nShow offline devices.",
            "text/markdown",
        )["documentId"])
        ingestion = RequirementIngestionService(
            JsonMapStore(self.root / "contexts.json"),
            document_provider=self.service.requirement_document,
        )
        context = ingestion.ingest({
            "sourceType": "UploadDocument",
            "documentId": parsed["documentId"],
            "projectId": "gridhub",
        })
        document = context["documents"][0]
        self.assertEqual("DocumentIngestion", document["source"])
        self.assertEqual("PRD", document["documentType"])
        self.assertGreaterEqual(document["pages"], 1)
        self.assertTrue(document["sections"])
        self.assertEqual(parsed["contentHash"], document["contentHash"])

    def test_ui_uploads_parses_then_ingests_document(self):
        source = (ROOT / "azure-devops-extension/src/newRequirementWorkspace.tsx").read_text()
        self.assertIn(".pdf,.docx,.txt,.md,.markdown", source)
        self.assertLess(source.index("/documents/upload"), source.index("/parse`"))
        self.assertLess(source.index("/parse`"), source.index("/requirements/ingest"))
        for label in ("Uploaded File", "Detected Type", "Pages", "Ready for Analysis"):
            self.assertIn(label, source)


def _docx_bytes() -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>""")
        archive.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>System Requirements</w:t></w:r></w:p>
<w:p><w:r><w:t>Software Requirements Specification for Alarm Center.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Non-Functional Requirements</w:t></w:r></w:p>
<w:p><w:r><w:t>The system shall load active alarms within two seconds.</w:t></w:r></w:p>
</w:body></w:document>""")
        archive.writestr("docProps/core.xml", """<?xml version="1.0"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Alarm Center SRS</dc:title><dc:creator>HEI Team</dc:creator></cp:coreProperties>""")
        archive.writestr("docProps/app.xml", """<?xml version="1.0"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Pages>4</Pages><Words>1200</Words></Properties>""")
    return output.getvalue()


def _pdf_bytes() -> bytes:
    stream = b"BT /F1 12 Tf 72 720 Td (Functional Specification for Alarm Center) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Title (Functional Specification) >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


if __name__ == "__main__":
    unittest.main()
