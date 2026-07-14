from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader

MAX_RESUME_BYTES = 5_000_000
SUPPORTED_SUFFIXES = {".txt", ".pdf", ".docx"}


class UnsupportedResumeError(ValueError):
    pass


def extract_resume_text(filename: str, content: bytes) -> str:
    if len(content) > MAX_RESUME_BYTES:
        raise UnsupportedResumeError("Resume exceeds the 5 MB upload limit")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedResumeError("Supported resume formats are .txt, .pdf, and .docx")

    try:
        if suffix == ".txt":
            text = content.decode("utf-8", errors="replace")
        elif suffix == ".pdf":
            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            document = Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception as exc:
        raise UnsupportedResumeError("The uploaded resume could not be parsed") from exc

    cleaned = text.strip()
    if len(cleaned) < 40:
        raise UnsupportedResumeError("The resume did not contain enough extractable text; scanned PDFs need OCR before upload")
    return cleaned
