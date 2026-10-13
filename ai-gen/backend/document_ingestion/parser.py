"""Deterministic parsers for supported enterprise requirement documents."""

from __future__ import annotations

import io
import math
import re
import zlib
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile, is_zipfile

from .models import DetectedDocumentType, DocumentFormat, DocumentSection, ParsedDocument


class DocumentParseError(ValueError):
    pass


class DocumentParser:
    def parse(self, content: bytes, document_format: DocumentFormat, file_name: str) -> tuple[ParsedDocument, list[dict[str, Any]]]:
        log = [{"stage": "ParseStarted", "status": "Completed", "message": f"Parsing {document_format.value}."}]
        if document_format == DocumentFormat.PDF:
            text, metadata, pages, sections, adapter = self._parse_pdf(content)
        elif document_format == DocumentFormat.DOCX:
            text, metadata, pages, sections, adapter = self._parse_docx(content)
        else:
            text = self._decode_text(content)
            metadata = {}
            sections = self._markdown_sections(text) if document_format == DocumentFormat.MARKDOWN else self._text_sections(text)
            pages = max(1, math.ceil(len(text) / 3000))
            adapter = "utf8"
        normalized = _normalize(text)
        if not normalized:
            raise DocumentParseError("The document contains no extractable text.")
        title = str(metadata.get("title") or "").strip() or _title_from_sections(sections) or _title_from_text(normalized) or Path(file_name).stem
        detected = detect_document_type(title, normalized)
        language = detect_language(normalized)
        metadata = {**metadata, "parser": adapter, "fileName": file_name}
        log.extend([
            {"stage": "TextExtracted", "status": "Completed", "message": f"Extracted {len(normalized)} characters."},
            {"stage": "TypeDetected", "status": "Completed", "message": f"Detected {detected.value}."},
            {"stage": "ParseCompleted", "status": "Completed", "message": f"Document is ready with {pages} page(s)."},
        ])
        return ParsedDocument(title, detected, sections, normalized, metadata, pages, language), log

    @staticmethod
    def _decode_text(content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "utf-16"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise DocumentParseError("The text document encoding is not supported.")

    def _parse_docx(self, content: bytes) -> tuple[str, dict[str, Any], int, list[DocumentSection], str]:
        if not is_zipfile(io.BytesIO(content)):
            raise DocumentParseError("The DOCX file is corrupted or is not an Open XML document.")
        try:
            with ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise DocumentParseError("The DOCX file does not contain word/document.xml.")
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                paragraphs: list[tuple[str, str]] = []
                for paragraph in root.findall(".//{*}p"):
                    text = "".join(node.text or "" for node in paragraph.findall(".//{*}t")).strip()
                    if not text:
                        continue
                    style_node = paragraph.find("./{*}pPr/{*}pStyle")
                    style = next((str(value) for key, value in (style_node.attrib.items() if style_node is not None else []) if key.endswith("}val") or key == "val"), "")
                    paragraphs.append((style, text))
                text = "\n".join(value for _, value in paragraphs)
                sections = self._docx_sections(paragraphs)
                metadata = self._docx_metadata(archive)
                pages = int(metadata.pop("pages", 0) or 0) or max(1, math.ceil(len(text) / 3000))
                return text, metadata, pages, sections, "openxml"
        except (BadZipFile, ElementTree.ParseError, KeyError) as error:
            raise DocumentParseError("The DOCX file is corrupted and could not be parsed.") from error

    @staticmethod
    def _docx_sections(paragraphs: list[tuple[str, str]]) -> list[DocumentSection]:
        sections: list[DocumentSection] = []
        current_title = "Document"
        current_level = 1
        body: list[str] = []
        for style, text in paragraphs:
            match = re.search(r"heading\s*([1-6])", style, re.IGNORECASE)
            if match:
                if body:
                    sections.append(DocumentSection(current_title, current_level, "\n".join(body)))
                current_title, current_level, body = text, int(match.group(1)), []
            else:
                body.append(text)
        if body or not sections:
            sections.append(DocumentSection(current_title, current_level, "\n".join(body)))
        return sections

    @staticmethod
    def _docx_metadata(archive: ZipFile) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        mappings = {
            "dc:title": "title", "dc:creator": "author", "cp:lastModifiedBy": "lastModifiedBy",
            "dcterms:created": "created", "dcterms:modified": "modified",
        }
        if "docProps/core.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("docProps/core.xml"))
            for node in root.iter():
                local = node.tag.rsplit("}", 1)[-1]
                prefix_key = next((key for key in mappings if key.endswith(f":{local}")), "")
                if prefix_key and node.text:
                    metadata[mappings[prefix_key]] = node.text
        if "docProps/app.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("docProps/app.xml"))
            for node in root.iter():
                local = node.tag.rsplit("}", 1)[-1]
                if local in {"Pages", "Words", "Company", "Application"} and node.text:
                    metadata[local[0].lower() + local[1:]] = int(node.text) if local in {"Pages", "Words"} and node.text.isdigit() else node.text
        return metadata

    def _parse_pdf(self, content: bytes) -> tuple[str, dict[str, Any], int, list[DocumentSection], str]:
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
            raise DocumentParseError("The PDF file is corrupted or incomplete.")
        if b"/Encrypt" in content:
            raise DocumentParseError("Encrypted PDF documents are not supported.")
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]

            reader = PdfReader(io.BytesIO(content), strict=False)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            metadata = {str(key).lstrip("/"): str(value) for key, value in (reader.metadata or {}).items() if value is not None}
            if "Title" in metadata:
                metadata["title"] = metadata.pop("Title")
            text = "\n\n".join(pages_text)
            return text, metadata, len(reader.pages), self._text_sections(text), "pypdf"
        except ImportError:
            return self._parse_pdf_fallback(content)
        except Exception as error:
            raise DocumentParseError("The PDF file could not be parsed.") from error

    def _parse_pdf_fallback(self, content: bytes) -> tuple[str, dict[str, Any], int, list[DocumentSection], str]:
        pages = len(re.findall(rb"/Type\s*/Page\b", content))
        if not pages:
            raise DocumentParseError("The PDF page structure is invalid.")
        metadata: dict[str, Any] = {}
        title_match = re.search(rb"/Title\s*\((.*?)\)", content, re.DOTALL)
        if title_match:
            metadata["title"] = _pdf_literal(title_match.group(1)).strip()
        streams: list[bytes] = []
        for match in re.finditer(rb"(<<.*?>>)\s*stream\r?\n(.*?)\r?\nendstream", content, re.DOTALL):
            header, stream = match.groups()
            if b"/FlateDecode" in header:
                try:
                    stream = zlib.decompress(stream)
                except zlib.error:
                    continue
            streams.append(stream)
        text_parts: list[str] = []
        for stream in streams:
            for literal in re.findall(rb"\((.*?)(?<!\\)\)\s*Tj", stream, re.DOTALL):
                text_parts.append(_pdf_literal(literal))
            for array in re.findall(rb"\[(.*?)\]\s*TJ", stream, re.DOTALL):
                text_parts.append("".join(_pdf_literal(item) for item in re.findall(rb"\((.*?)(?<!\\)\)", array, re.DOTALL)))
        text = "\n".join(part for part in text_parts if part.strip())
        return text, metadata, pages, self._text_sections(text), "pdf-fallback"

    @staticmethod
    def _markdown_sections(text: str) -> list[DocumentSection]:
        sections: list[DocumentSection] = []
        title, level, body = "Document", 1, []
        for line in text.splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                if body:
                    sections.append(DocumentSection(title, level, "\n".join(body).strip()))
                title, level, body = match.group(2).strip(), len(match.group(1)), []
            else:
                body.append(line)
        if body or not sections:
            sections.append(DocumentSection(title, level, "\n".join(body).strip()))
        return sections

    @staticmethod
    def _text_sections(text: str) -> list[DocumentSection]:
        lines = [line.strip() for line in text.splitlines()]
        sections: list[DocumentSection] = []
        title, body = "Document", []
        for line in lines:
            is_heading = bool(line) and len(line) <= 90 and (line.endswith(":") or (len(line.split()) <= 8 and line.isupper()))
            if is_heading:
                if body:
                    sections.append(DocumentSection(title, 1, "\n".join(body).strip()))
                title, body = line.rstrip(":"), []
            elif line:
                body.append(line)
        if body or not sections:
            sections.append(DocumentSection(title, 1, "\n".join(body).strip()))
        return sections


def detect_document_type(title: str, text: str) -> DetectedDocumentType:
    sample = f"{title}\n{text[:50000]}".lower()
    scores = {
        DetectedDocumentType.PRD: _hits(sample, ["product requirements document", "product requirement", "product vision", "target users", "product goals"]),
        DetectedDocumentType.BRD: _hits(sample, ["business requirements document", "business requirement", "business objective", "stakeholders", "business process"]),
        DetectedDocumentType.SRS: _hits(sample, ["software requirements specification", "system requirements", "non-functional requirements", "system interfaces", "technical requirements"]),
        DetectedDocumentType.FUNCTIONAL_SPECIFICATION: _hits(sample, ["functional specification", "functional requirements", "use cases", "functional behavior", "business rules"]),
    }
    detected, score = max(scores.items(), key=lambda item: item[1])
    return detected if score > 0 else DetectedDocumentType.UNKNOWN


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return "und"
    english_markers = {"the", "and", "for", "with", "shall", "user", "system", "requirement", "business"}
    return "en" if english_markers.intersection(words) or sum(character.isascii() for character in text) / max(1, len(text)) > 0.95 else "und"


def _hits(text: str, phrases: list[str]) -> int:
    return sum(2 if phrase in text else 0 for phrase in phrases)


def _normalize(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.replace("\x00", "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _title_from_sections(sections: list[DocumentSection]) -> str:
    return next((section.title for section in sections if section.title and section.title != "Document"), "")


def _title_from_text(text: str) -> str:
    first = next((line.strip("# ") for line in text.splitlines() if line.strip()), "")
    return first if len(first) <= 180 else ""


def _pdf_literal(value: bytes) -> str:
    value = re.sub(rb"\\([nrtbf])", lambda match: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}[match.group(1)], value)
    value = re.sub(rb"\\([()\\])", rb"\1", value)
    value = re.sub(rb"\\([0-7]{1,3})", lambda match: bytes([int(match.group(1), 8) % 256]), value)
    return value.decode("utf-8", errors="replace")
