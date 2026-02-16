from pathlib import Path

from app.modules.doc_extract.extract_doc import extract


def test_extract_txt_normalizes(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("Hello\n\nworld", encoding="utf-8")
    text = extract(str(path))
    assert text == "Hello world"


def test_extract_docx(tmp_path):
    try:
        import docx  # type: ignore
    except Exception:  # pragma: no cover - environment issue
        return

    path = tmp_path / "sample.docx"
    doc = docx.Document()
    doc.add_paragraph("First")
    doc.add_paragraph("Second")
    doc.save(str(path))

    text = extract(str(path))
    assert "First" in text and "Second" in text
