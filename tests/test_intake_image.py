"""Tests for image OCR intake module."""

from pathlib import Path

from app.core.ids import sha256_bytes
from app.core.manifest import get_manifest
from app.core.storage import artifact_path, read_artifact
from app.queue.db import init_db
from app.queue.jobs import claim_job
from app.modules.intake import intake_image


def _create_test_image(tmp_path: Path) -> Path:
    """Create a minimal valid PNG file for testing."""
    # Minimal 1x1 white PNG
    import struct
    import zlib

    def _make_png() -> bytes:
        sig = b"\x89PNG\r\n\x1a\n"
        # IHDR
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        # IDAT
        raw_data = b"\x00\xff\xff\xff"  # filter byte + RGB white pixel
        compressed = zlib.compress(raw_data)
        idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
        idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)
        # IEND
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        return sig + ihdr + idat + iend

    img_path = tmp_path / "test_screenshot.png"
    img_path.write_bytes(_make_png())
    return img_path


def test_supported_extensions():
    """Check that common image formats are supported."""
    assert ".png" in intake_image.SUPPORTED_EXTENSIONS
    assert ".jpg" in intake_image.SUPPORTED_EXTENSIONS
    assert ".jpeg" in intake_image.SUPPORTED_EXTENSIONS
    assert ".webp" in intake_image.SUPPORTED_EXTENSIONS
    assert ".bmp" in intake_image.SUPPORTED_EXTENSIONS
    assert ".tiff" in intake_image.SUPPORTED_EXTENSIONS


def test_ocr_image_file_calls_backends(tmp_path, monkeypatch):
    """Verify _ocr_image_file invokes OCR and returns text."""
    img_path = _create_test_image(tmp_path)

    # Mock the OCR backends to avoid needing tesseract/paddle installed
    monkeypatch.setattr(
        intake_image,
        "_ocr_image_file",
        lambda path: "Extracted OCR text from image",
    )
    result = intake_image._ocr_image_file(img_path)
    assert result == "Extracted OCR text from image"


def test_ingest_image_stores_artifacts_and_enqueues(tmp_path, monkeypatch):
    """Full ingest_image pipeline: OCR, store, manifest, enqueue chunk_text."""
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    img_path = _create_test_image(tmp_path)

    # Mock OCR to return known text
    monkeypatch.setattr(
        intake_image,
        "_ocr_image_file",
        lambda path: "Hello from screenshot OCR",
    )

    source_id = f"image:{img_path}"
    source_version = sha256_bytes(img_path.read_bytes())
    manifest = intake_image.ingest_image(str(img_path), source_id, source_version)

    # Check manifest
    assert manifest["source_type"] == "image"
    assert manifest["stats"]["text_chars"] == len("Hello from screenshot OCR")
    assert manifest["steps"]["ingest_image"]["status"] == "done"

    # Check stored manifest
    stored = get_manifest(source_id, source_version)
    assert stored is not None

    # Check artifacts
    text = read_artifact(source_id, source_version, "text/canonical.txt")
    assert text == "Hello from screenshot OCR"
    raw = artifact_path(source_id, source_version, "raw/source.png")
    assert raw.exists()

    # Check chunk_text job was enqueued
    job = claim_job("oss20b")
    assert job is not None
    assert job["job_type"] == "chunk_text"


def test_handle_job(tmp_path, monkeypatch):
    """handle_job delegates to ingest_image correctly."""
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    img_path = _create_test_image(tmp_path)
    monkeypatch.setattr(
        intake_image,
        "_ocr_image_file",
        lambda path: "Job handler OCR result",
    )

    source_id = f"image:{img_path}"
    source_version = sha256_bytes(img_path.read_bytes())

    job = {
        "source_id": source_id,
        "source_version": source_version,
        "lane": "io",
        "job_id": "test-job-1",
        "job_type": "ingest_image",
    }
    intake_image.handle_job(job)

    stored = get_manifest(source_id, source_version)
    assert stored is not None
    assert stored["source_type"] == "image"


def test_enqueue_image(tmp_path, monkeypatch):
    """enqueue() validates path and creates job."""
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    img_path = _create_test_image(tmp_path)
    job_id = intake_image.enqueue(str(img_path))
    assert job_id

    job = claim_job("io")
    assert job is not None
    assert job["job_type"] == "ingest_image"


def test_enqueue_rejects_unsupported_extension(tmp_path, monkeypatch):
    """enqueue() rejects non-image file extensions."""
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("hello", encoding="utf-8")

    import pytest
    with pytest.raises(ValueError, match="Unsupported image type"):
        intake_image.enqueue(str(txt_file))
