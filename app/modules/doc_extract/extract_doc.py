"""Document extraction for PDF/DOCX/TXT."""

from __future__ import annotations

from pathlib import Path
from typing import List

from app.core.textnorm import normalize_whitespace


def _extract_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_docx(path: Path) -> str:
    try:
        import docx  # type: ignore
    except Exception as exc:
        raise RuntimeError("python-docx not installed") from exc
    document = docx.Document(str(path))
    parts: List[str] = []
    for para in document.paragraphs:
        if para.text:
            parts.append(para.text)
    return "\n".join(parts)


def _extract_pdf(path: Path) -> str:
    try:
        import pypdfium2 as pdfium  # type: ignore
    except Exception as exc:
        raise RuntimeError("pypdfium2 not installed") from exc

    doc = pdfium.PdfDocument(str(path))
    parts: List[str] = []
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            textpage = page.get_textpage()
            try:
                parts.append(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
    finally:
        doc.close()
    return "\n".join(parts)


def extract(path: str) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        text = _extract_txt(file_path)
    elif suffix == ".docx":
        text = _extract_docx(file_path)
    elif suffix == ".pdf":
        text = _extract_pdf(file_path)
    else:
        raise ValueError(f"Unsupported document type: {suffix}")
    return normalize_whitespace(text)
