"""Intake image: OCR text from standalone image files, store artifacts, update manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from app.core.ids import make_source_id, parse_source_id, sha256_file
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import read_artifact, write_artifact, write_artifact_bytes
from app.core.textnorm import normalize_whitespace
from app.core.timeutil import utc_now
from app.modules.security.ingest_allowlist import ensure_ingest_path_allowed
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
RAW_IMAGE_PATH = "raw/source"
CANONICAL_TEXT_PATH = "text/canonical.txt"


def _ocr_image_file(path: Path) -> str:
    """Run OCR on a standalone image file, reusing the doc_extract OCR backends."""
    from app.modules.doc_extract.extract_doc import (
        _build_paddle_ocr_reader,
        _ocr_image_with_paddle,
        _ocr_image_with_tesseract,
        _pdf_ocr_backend_order,
    )

    try:
        from PIL import Image  # type: ignore
    except Exception as exc:
        raise RuntimeError("Pillow not installed") from exc

    image = Image.open(str(path))
    backend_order = _pdf_ocr_backend_order()
    paddle_reader = _build_paddle_ocr_reader() if "paddleocr" in backend_order else None

    text = ""
    try:
        for backend in backend_order:
            if backend == "paddleocr" and paddle_reader is not None:
                text = _ocr_image_with_paddle(image, paddle_reader)
            elif backend == "tesseract":
                text = _ocr_image_with_tesseract(image)
            if text:
                break
    finally:
        if hasattr(image, "close"):
            image.close()

    return normalize_whitespace(text)


def enqueue(path: str) -> str:
    """Validate and enqueue an image file for OCR ingest."""
    abs_path = str(ensure_ingest_path_allowed(Path(path), source="ingest_image_enqueue"))
    file_path = Path(abs_path)
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported image type: {file_path.suffix}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    source_id = make_source_id("image", abs_path)
    source_version = sha256_file(file_path)
    return enqueue_job("ingest_image", "io", source_id, source_version)


def ingest_image(path: str, source_id: str, source_version: str) -> Dict[str, object]:
    """OCR an image, store artifacts, update manifest, and enqueue chunking."""
    existing = get_manifest(source_id, source_version)
    if existing:
        existing_text = read_artifact(source_id, source_version, CANONICAL_TEXT_PATH)
        if existing_text:
            return existing

    file_path = Path(path)
    text = _ocr_image_file(file_path)

    raw_rel = f"{RAW_IMAGE_PATH}{file_path.suffix.lower()}"
    write_artifact_bytes(source_id, source_version, raw_rel, file_path.read_bytes())
    write_artifact(source_id, source_version, CANONICAL_TEXT_PATH, text)

    manifest = dict(existing or {})
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    artifacts.update(
        {
            "raw_image": raw_rel,
            "canonical_text": CANONICAL_TEXT_PATH,
        }
    )
    steps = manifest.get("steps")
    if not isinstance(steps, dict):
        steps = {}
    steps["ingest_image"] = {"status": "done"}
    manifest.update(
        {
            "source_id": source_id,
            "source_version": source_version,
            "source_type": "image",
            "source_uri": str(file_path),
            "artifacts": artifacts,
            "stats": {
                "text_chars": len(text),
                "text_words": len(text.split()) if text else 0,
            },
            "updated_at": utc_now().isoformat(),
            "steps": steps,
        }
    )
    upsert_manifest(source_id, source_version, manifest)
    enqueue_job("chunk_text", "oss20b", source_id, source_version)
    return manifest


def handle_job(job: Dict[str, object]) -> None:
    """Worker handler for ingest_image jobs."""
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])
    kind, value = parse_source_id(source_id)
    if kind != "image":
        raise ValueError(f"Expected image source_id, got {source_id}")

    run_id = log_run(
        lane=str(job.get("lane", "io")),
        component="intake_image",
        input_json={"source_id": source_id, "source_version": source_version, "path": value},
    )

    try:
        manifest = ingest_image(value, source_id, source_version)
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_image",
            input_json={"run_id": run_id},
            output_json={"artifacts": manifest.get("artifacts", {})},
        )
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_image",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
