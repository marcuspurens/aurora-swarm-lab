from app.modules.intake.ingest_auto import enqueue_items, extract_items
from app.core.manifest import get_manifest


def test_extract_items_supports_file_uri_and_url(tmp_path):
    doc = tmp_path / "note.txt"
    doc.write_text("hello", encoding="utf-8")
    text = f"https://example.com/story).\nfile://{doc}\n"

    out = extract_items(text=text)
    assert "https://example.com/story" in out
    assert str(doc.resolve()) in out


def test_enqueue_items_ingests_file_uri(db, ingest_allowlist):
    doc = ingest_allowlist / "brief.md"
    doc.write_text("content", encoding="utf-8")
    items = [f"file://{doc}"]
    out = enqueue_items(items)

    assert len(out) == 1
    assert out[0]["kind"] == "doc"
    assert out[0]["result"]["job_id"]


def test_enqueue_items_blocks_file_when_allowlist_missing(tmp_path, db, monkeypatch):
    monkeypatch.delenv("AURORA_INGEST_PATH_ALLOWLIST", raising=False)
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST_ENFORCED", "1")

    doc = tmp_path / "brief.md"
    doc.write_text("content", encoding="utf-8")
    out = enqueue_items([f"file://{doc}"])

    assert len(out) == 1
    assert out[0]["kind"] == "error"
    assert "allowlist" in str(out[0]["error"]).lower()


def test_enqueue_items_supports_folder_input(db, ingest_allowlist):
    folder = ingest_allowlist / "inbox"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "a.md").write_text("a", encoding="utf-8")
    (folder / "b.txt").write_text("b", encoding="utf-8")

    out = enqueue_items([str(folder)])
    docs = [item for item in out if item.get("kind") == "doc"]

    assert len(docs) == 2
    assert all(item["result"]["job_id"] for item in docs)


def test_enqueue_items_folder_respects_max_files_limit(db, ingest_allowlist, monkeypatch):
    monkeypatch.setenv("AURORA_INGEST_AUTO_MAX_FILES_PER_DIR", "1")

    folder = ingest_allowlist / "inbox"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "a.md").write_text("a", encoding="utf-8")
    (folder / "b.txt").write_text("b", encoding="utf-8")

    out = enqueue_items([str(folder)])
    docs = [item for item in out if item.get("kind") == "doc"]
    warnings = [item for item in out if item.get("kind") == "folder" and item.get("warning")]

    assert len(docs) == 1
    assert warnings


def test_enqueue_items_seeds_intake_tags_and_context(db, ingest_allowlist):
    doc = ingest_allowlist / "brief.md"
    doc.write_text("content", encoding="utf-8")
    out = enqueue_items([str(doc)], tags=["python", "graph"], context="PEP review notes")

    assert len(out) == 1
    source_id = out[0]["result"]["source_id"]
    source_version = out[0]["result"]["source_version"]
    manifest = get_manifest(source_id, source_version)
    assert manifest is not None
    intake = ((manifest.get("metadata") or {}).get("intake") or {})
    assert intake.get("tags") == ["python", "graph"]
    assert intake.get("context") == "PEP review notes"


def test_enqueue_items_merges_intake_tags_without_duplicates(db, ingest_allowlist):
    doc = ingest_allowlist / "brief.md"
    doc.write_text("content", encoding="utf-8")
    first = enqueue_items([str(doc)], tags=["Python", "Graph"], context="First")[0]["result"]
    enqueue_items([str(doc)], tags=["graph", "ops"], context="Second")

    manifest = get_manifest(first["source_id"], first["source_version"])
    assert manifest is not None
    intake = ((manifest.get("metadata") or {}).get("intake") or {})
    assert intake.get("tags") == ["Python", "Graph", "ops"]
    assert intake.get("context") == "Second"


def test_enqueue_items_seeds_structured_source_metadata(db, ingest_allowlist):
    doc = ingest_allowlist / "brief.md"
    doc.write_text("content", encoding="utf-8")
    out = enqueue_items(
        [str(doc)],
        speaker="Philipp Roth",
        organization="ORF",
        event_date="2025-06-24",
        source_metadata={"organization_uri": "https://en.wikipedia.org/wiki/ORF_(broadcaster)", "title": "From Ontology to Knowledge Graph"},
    )

    result = out[0]["result"]
    manifest = get_manifest(result["source_id"], result["source_version"])
    assert manifest is not None
    metadata = manifest.get("metadata") or {}
    intake = metadata.get("intake") or {}
    source_metadata = intake.get("source_metadata") or {}
    assert source_metadata.get("speaker") == "Philipp Roth"
    assert source_metadata.get("organization") == "ORF"
    assert source_metadata.get("event_date") == "2025-06-24"
    assert source_metadata.get("organization_uri") == "https://en.wikipedia.org/wiki/ORF_(broadcaster)"

    ebucore_plus = metadata.get("ebucore_plus") or {}
    assert ebucore_plus.get("schema") == "ebucore_plus.intake.v1"
    assert (ebucore_plus.get("speaker") or {}).get("name") == "Philipp Roth"
    assert (ebucore_plus.get("organization") or {}).get("name") == "ORF"
    assert (ebucore_plus.get("organization") or {}).get("uri") == "https://en.wikipedia.org/wiki/ORF_(broadcaster)"
    assert ebucore_plus.get("event_date") == "2025-06-24"
