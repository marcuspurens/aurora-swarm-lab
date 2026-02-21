from app.modules.graph import extract_relations
from app.queue.db import init_db
from app.core.storage import write_artifact, read_artifact
from app.core.manifest import upsert_manifest
from app.core.models import GraphRelationsOutput, GraphRelation


def test_graph_extract_relations(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v1"
    write_artifact(
        source_id,
        source_version,
        "enrich/chunks.jsonl",
        "{\"doc_id\": \"x\", \"segment_id\": \"chunk_1\", \"text\": \"hello\"}\n",
    )
    write_artifact(
        source_id,
        source_version,
        "graph/entities.jsonl",
        "{\"entity_id\": \"e1\", \"name\": \"Acme\", \"type\": \"Org\"}\n",
    )
    write_artifact(
        source_id,
        source_version,
        "graph/ontology.json",
        "[{\"predicate\":\"related_to\",\"domain_type\":\"Entity\",\"range_type\":\"Entity\",\"description\":\"x\"}]",
    )
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {
                "enriched_chunks": "enrich/chunks.jsonl",
                "graph_entities": "graph/entities.jsonl",
                "ontology": "graph/ontology.json",
            },
        },
    )

    def fake_generate(prompt, model, schema):
        return GraphRelationsOutput(
            relations=[
                GraphRelation(
                    rel_id="r1",
                    subj_entity_id="e1",
                    predicate="related_to",
                    obj_entity_id="e1",
                    doc_id="x",
                    segment_id="chunk_1",
                    confidence=0.6,
                )
            ]
        )

    monkeypatch.setattr(extract_relations, "generate_json", fake_generate)

    extract_relations.handle_job({"source_id": source_id, "source_version": source_version})

    rel = read_artifact(source_id, source_version, "graph/relations.jsonl")
    assert rel is not None


def test_graph_extract_relations_filters_invalid_predicate(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v2"
    write_artifact(
        source_id,
        source_version,
        "enrich/chunks.jsonl",
        "{\"doc_id\": \"x\", \"segment_id\": \"chunk_1\", \"text\": \"hello\"}\n",
    )
    write_artifact(
        source_id,
        source_version,
        "graph/entities.jsonl",
        "{\"entity_id\": \"e1\", \"name\": \"Acme\", \"type\": \"Org\"}\n",
    )
    write_artifact(
        source_id,
        source_version,
        "graph/ontology.json",
        "[{\"predicate\":\"related_to\",\"domain_type\":\"Entity\",\"range_type\":\"Entity\",\"description\":\"x\"}]",
    )
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {
                "enriched_chunks": "enrich/chunks.jsonl",
                "graph_entities": "graph/entities.jsonl",
                "ontology": "graph/ontology.json",
            },
        },
    )

    def fake_generate(prompt, model, schema):
        return GraphRelationsOutput(
            relations=[
                GraphRelation(
                    rel_id="r-valid",
                    subj_entity_id="e1",
                    predicate="related_to",
                    obj_entity_id="e1",
                    doc_id="x",
                    segment_id="chunk_1",
                    confidence=0.6,
                ),
                GraphRelation(
                    rel_id="r-invalid",
                    subj_entity_id="e1",
                    predicate="unsupported_link",
                    obj_entity_id="e1",
                    doc_id="x",
                    segment_id="chunk_1",
                    confidence=0.6,
                ),
            ]
        )

    monkeypatch.setattr(extract_relations, "generate_json", fake_generate)
    extract_relations.handle_job({"source_id": source_id, "source_version": source_version})

    rel = read_artifact(source_id, source_version, "graph/relations.jsonl")
    invalid = read_artifact(source_id, source_version, "graph/relations_invalid.jsonl")
    assert rel is not None
    assert "r-valid" in rel
    assert "r-invalid" not in rel
    assert invalid is not None
    assert "predicate_not_in_ontology" in invalid


def test_graph_extract_relations_accepts_document_mentions(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com/doc"
    source_version = "v3"
    write_artifact(
        source_id,
        source_version,
        "enrich/chunks.jsonl",
        "{\"doc_id\": \"doc-1\", \"segment_id\": \"chunk_1\", \"text\": \"hello\"}\n",
    )
    write_artifact(
        source_id,
        source_version,
        "graph/entities.jsonl",
        "{\"entity_id\": \"e1\", \"name\": \"Acme\", \"type\": \"Org\"}\n",
    )
    write_artifact(
        source_id,
        source_version,
        "graph/ontology.json",
        "[{\"predicate\":\"mentions\",\"domain_type\":\"Document\",\"range_type\":\"Entity\",\"description\":\"x\"}]",
    )
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {
                "enriched_chunks": "enrich/chunks.jsonl",
                "graph_entities": "graph/entities.jsonl",
                "ontology": "graph/ontology.json",
            },
        },
    )

    def fake_generate(prompt, model, schema):
        return GraphRelationsOutput(
            relations=[
                GraphRelation(
                    rel_id="r1",
                    subj_entity_id="doc-1",
                    predicate="mentions",
                    obj_entity_id="e1",
                    doc_id="doc-1",
                    segment_id="chunk_1",
                    confidence=0.9,
                )
            ]
        )

    monkeypatch.setattr(extract_relations, "generate_json", fake_generate)
    extract_relations.handle_job({"source_id": source_id, "source_version": source_version})

    rel = read_artifact(source_id, source_version, "graph/relations.jsonl")
    invalid = read_artifact(source_id, source_version, "graph/relations_invalid.jsonl")
    assert rel is not None
    assert "r1" in rel
    assert invalid is None


def test_graph_extract_relations_respects_max_chunks_env(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("AURORA_GRAPH_RELATIONS_MAX_CHUNKS", "1")
    init_db()

    source_id = "url:https://example.com/chunks"
    source_version = "v4"
    write_artifact(
        source_id,
        source_version,
        "enrich/chunks.jsonl",
        (
            "{\"doc_id\": \"x\", \"segment_id\": \"chunk_1\", \"text\": \"hello\"}\n"
            "{\"doc_id\": \"x\", \"segment_id\": \"chunk_2\", \"text\": \"world\"}\n"
        ),
    )
    write_artifact(
        source_id,
        source_version,
        "graph/entities.jsonl",
        "{\"entity_id\": \"e1\", \"name\": \"Acme\", \"type\": \"Org\"}\n",
    )
    write_artifact(
        source_id,
        source_version,
        "graph/ontology.json",
        "[{\"predicate\":\"related_to\",\"domain_type\":\"Entity\",\"range_type\":\"Entity\",\"description\":\"x\"}]",
    )
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {
                "enriched_chunks": "enrich/chunks.jsonl",
                "graph_entities": "graph/entities.jsonl",
                "ontology": "graph/ontology.json",
            },
        },
    )

    def fake_generate(prompt, model, schema):
        assert "chunk_1" in prompt
        assert "chunk_2" not in prompt
        return GraphRelationsOutput(
            relations=[
                GraphRelation(
                    rel_id="r1",
                    subj_entity_id="e1",
                    predicate="related_to",
                    obj_entity_id="e1",
                    doc_id="x",
                    segment_id="chunk_1",
                    confidence=0.9,
                )
            ]
        )

    monkeypatch.setattr(extract_relations, "generate_json", fake_generate)
    extract_relations.handle_job({"source_id": source_id, "source_version": source_version})

    rel = read_artifact(source_id, source_version, "graph/relations.jsonl")
    assert rel is not None
    assert "r1" in rel
