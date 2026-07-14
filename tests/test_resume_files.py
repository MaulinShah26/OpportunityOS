from io import BytesIO

import pytest
from docx import Document

from opportunityos.infrastructure.resume import UnsupportedResumeError, extract_resume_text


def test_extracts_txt_resume() -> None:
    text = extract_resume_text(
        "resume.txt",
        b"Senior data scientist with product analytics, retention and experimentation experience.",
    )
    assert "product analytics" in text


def test_extracts_docx_resume() -> None:
    document = Document()
    document.add_paragraph(
        "Senior data scientist with product analytics, retention and experimentation experience."
    )
    buffer = BytesIO()
    document.save(buffer)
    text = extract_resume_text("resume.docx", buffer.getvalue())
    assert "retention" in text


def test_rejects_unsupported_resume() -> None:
    with pytest.raises(UnsupportedResumeError):
        extract_resume_text("resume.exe", b"not a supported resume format" * 4)
