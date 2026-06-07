from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader
from upload_security import UploadParserConfig, UploadParseResult, parse_document_bytes

@dataclass(frozen=True)
class LabUploadResult:
    fixture_id: str
    parser_result: UploadParseResult

def run_synthetic_upload_fixture(
    loader: SyntheticFixtureLoader,
    *,
    fixture_id: str,
    parser_config: UploadParserConfig,
) -> LabUploadResult:
    fixture = loader.load_fixture_by_id(fixture_id, prefix="uploads/")
    upload_kind = str(fixture.get("upload_kind") or "")
    filename = str(fixture.get("filename") or "synthetic.txt")
    if upload_kind == "safe_text":
        text = str(fixture.get("content") or "synthetic observation text")
        raw = text.encode("utf-8")
    elif upload_kind == "hostile_pdf":
        raw = b"%PDF-1.4\n1 0 obj<</OpenAction<</S/JavaScript/JS(alert)>> >>endobj\n%%EOF"
    elif upload_kind == "hostile_docx":
        raw = _hostile_docx_bytes()
    else:
        raise LabFixtureError("Synthetic upload fixture kind is unsupported.")
    return LabUploadResult(
        fixture_id=fixture_id,
        parser_result=parse_document_bytes(raw, filename, str(fixture.get("content_type") or ""), parser_config),
    )

def _hostile_docx_bytes() -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", "<w:document><w:body><w:p>synthetic</w:p></w:body></w:document>")
        zf.writestr("word/vbaProject.bin", b"synthetic macro marker")
    return bio.getvalue()
