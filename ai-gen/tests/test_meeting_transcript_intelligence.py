from __future__ import annotations

import base64
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.document_ingestion import DocumentIngestionService
from backend.platform.shared import JsonMapStore
from backend.requirement_intake import RequirementIngestionService
from backend.transcript_intelligence import (
    TranscriptAnalyzer,
    TranscriptIntelligenceService,
    build_transcript_intelligence_router,
)


TRANSCRIPT = """Meeting Title: Device Health Review
Date: 2026-07-20
[00:01] Priya: Good morning everyone.
[00:10] Priya: We agreed that the dashboard will focus on unhealthy devices.
[00:20] Alex: Operations users must filter devices by health status and communication state.
[00:30] Sam: The dashboard requires the telemetry API and Device Health service.
[00:40] Alex: Operations users must filter devices by health status and communication state.
[00:50] Priya: Action item: Sam will confirm the API response fields.
[01:00] Sam: There is a risk that stale telemetry could show a healthy device as online.
[01:10] Alex: Do we need a separate permission for field technicians?
[01:20] Priya: Thanks everyone.
"""


class MeetingTranscriptIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.documents = DocumentIngestionService(root / "documents")
        self.requirements = RequirementIngestionService(JsonMapStore(root / "requirements.json"))
        self.service = TranscriptIntelligenceService(
            root / "transcripts",
            document_service=self.documents,
            requirement_ingestion=self.requirements,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_analyzer_extracts_engineering_findings_and_removes_noise(self) -> None:
        result = TranscriptAnalyzer().analyze(TRANSCRIPT)
        self.assertEqual(result.meeting_title, "Device Health Review")
        self.assertEqual(result.meeting_date, "2026-07-20")
        self.assertEqual(result.participants, ["Priya", "Alex", "Sam"])
        self.assertTrue(result.ready_for_planning)
        self.assertEqual(len(result.requirements), 2)
        self.assertEqual(len(result.decisions), 1)
        self.assertEqual(len(result.action_items), 1)
        self.assertEqual(len(result.risks), 1)
        self.assertEqual(len(result.open_questions), 1)
        self.assertEqual(len(result.dependencies), 1)
        self.assertEqual(result.duplicate_lines_removed, 1)
        all_findings = " ".join(item.text for item in result.requirements + result.decisions + result.action_items)
        self.assertNotIn("Good morning", all_findings)
        self.assertNotIn("Thanks everyone", all_findings)

    def test_teams_zoom_and_plain_text_sources_are_supported(self) -> None:
        for source in ("TeamsTranscript", "ZoomTranscript", "TextTranscript"):
            uploaded = self.service.upload({"sourceType": source, "title": "Review", "transcript": TRANSCRIPT})
            analyzed = self.service.analyze(uploaded["transcriptId"])
            self.assertEqual(analyzed["sourceType"], source)
            self.assertTrue(analyzed["readyForPlanning"])

    def test_teams_speaker_header_format_preserves_participants_and_evidence(self) -> None:
        result = TranscriptAnalyzer().analyze("""Meeting Title: Alarm Review
Participants: Maya, Jordan
July 20, 2026
Maya 0:03
Operations users must acknowledge critical alarms.
Jordan 0:18
We decided to retain an audit record for every acknowledgement.
""")
        self.assertEqual(result.participants, ["Maya", "Jordan"])
        self.assertEqual(result.meeting_date, "July 20, 2026")
        self.assertEqual(result.requirements[0].speaker, "Maya")
        self.assertEqual(result.requirements[0].timestamp, "0:03")

    def test_analysis_creates_curated_requirement_context(self) -> None:
        uploaded = self.service.upload({
            "sourceType": "TeamsTranscript",
            "transcript": TRANSCRIPT,
            "projectId": "project-1",
            "projectName": "LineDefender",
            "actor": "Priya",
            "correlationId": "corr-meeting",
        })
        analyzed = self.service.analyze(uploaded["transcriptId"])
        context = self.requirements.get(analyzed["requirementContextId"])
        self.assertIsNotNone(context)
        normalized = str(context["normalizedRequirement"])
        self.assertIn("Engineering Requirements", normalized)
        self.assertIn("Operations users must filter devices", normalized)
        self.assertIn("Business Decisions", normalized)
        self.assertNotIn("Good morning", normalized)
        self.assertNotIn("Thanks everyone", normalized)
        self.assertEqual(context["metadata"]["sourceReference"], uploaded["transcriptId"])

    def test_no_explicit_requirement_requires_review_and_does_not_create_context(self) -> None:
        uploaded = self.service.upload({
            "sourceType": "TextTranscript",
            "title": "Weekly Catch-up",
            "transcript": "Alex: Good morning everyone.\nSam: Thanks everyone.",
            "projectId": "project-1",
        })
        analyzed = self.service.analyze(uploaded["transcriptId"])
        self.assertEqual(analyzed["status"], "NeedsReview")
        self.assertFalse(analyzed["readyForPlanning"])
        self.assertEqual(analyzed["requirementContextId"], "")
        self.assertTrue(analyzed["analysis"]["warnings"])

    def test_txt_document_is_parsed_through_document_ingestion(self) -> None:
        uploaded = self.service.upload({
            "sourceType": "TXT",
            "fileName": "meeting.txt",
            "mediaType": "text/plain",
            "contentBase64": base64.b64encode(TRANSCRIPT.encode()).decode(),
        })
        self.assertTrue(uploaded["documentId"].startswith("document_"))
        self.assertTrue(self.service.analyze(uploaded["transcriptId"])["readyForPlanning"])

    def test_docx_document_is_parsed_through_document_ingestion(self) -> None:
        uploaded = self.service.upload({
            "sourceType": "DOCX",
            "fileName": "meeting.docx",
            "mediaType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "contentBase64": base64.b64encode(_docx(TRANSCRIPT)).decode(),
        })
        analyzed = self.service.analyze(uploaded["transcriptId"])
        self.assertEqual(analyzed["sourceType"], "DOCX")
        self.assertTrue(analyzed["readyForPlanning"])

    def test_api_upload_analyze_and_get(self) -> None:
        app = FastAPI()
        app.include_router(build_transcript_intelligence_router(self.service))
        client = TestClient(app)
        uploaded = client.post("/transcripts/upload", json={"sourceType": "TeamsTranscript", "transcript": TRANSCRIPT, "projectId": "project-1"})
        self.assertEqual(uploaded.status_code, 200)
        transcript_id = uploaded.json()["transcriptId"]
        analyzed = client.post("/transcripts/analyze", json={"transcriptId": transcript_id})
        self.assertEqual(analyzed.status_code, 200)
        self.assertTrue(analyzed.json()["readyForPlanning"])
        loaded = client.get(f"/transcripts/{transcript_id}")
        self.assertEqual(loaded.status_code, 200)
        self.assertNotIn("transcript", loaded.json())

    def test_api_rejects_missing_or_unknown_transcript(self) -> None:
        app = FastAPI()
        app.include_router(build_transcript_intelligence_router(self.service))
        client = TestClient(app)
        self.assertEqual(client.post("/transcripts/upload", json={"sourceType": "TextTranscript", "transcript": ""}).status_code, 400)
        self.assertEqual(client.post("/transcripts/analyze", json={}).status_code, 400)
        self.assertEqual(client.get("/transcripts/missing").status_code, 404)


def _docx(text: str) -> bytes:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in escaped.splitlines())
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"xml\" ContentType=\"application/xml\"/></Types>")
        archive.writestr("word/document.xml", f"<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>{paragraphs}</w:body></w:document>")
    return stream.getvalue()


if __name__ == "__main__":
    unittest.main()
