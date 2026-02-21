from app.modules.graph.ontology_rules import canonical_default_rules, validate_relations


def test_validate_relations_accepts_related_to_entity_wildcard():
    rules = canonical_default_rules()
    relations = [
        {
            "rel_id": "r1",
            "subj_entity_id": "e1",
            "predicate": "related_to",
            "obj_entity_id": "e2",
            "doc_id": "d",
            "segment_id": "s",
            "confidence": 0.7,
        }
    ]
    entity_types = {"e1": "Org", "e2": "Org"}
    out = validate_relations(relations, entity_types=entity_types, rules=rules)
    assert out["summary"]["invalid"] == 0
    assert out["summary"]["valid"] == 1


def test_validate_relations_accepts_mentions_entity_to_entity():
    rules = canonical_default_rules()
    relations = [
        {
            "rel_id": "r1",
            "subj_entity_id": "e1",
            "predicate": "mentions",
            "obj_entity_id": "e2",
            "doc_id": "d",
            "segment_id": "s",
            "confidence": 0.7,
        }
    ]
    entity_types = {"e1": "Organisation", "e2": "Standard"}
    out = validate_relations(relations, entity_types=entity_types, rules=rules)
    assert out["summary"]["invalid"] == 0
    assert out["summary"]["valid"] == 1


def test_validate_relations_rejects_unknown_predicate():
    rules = canonical_default_rules()
    relations = [
        {
            "rel_id": "r1",
            "subj_entity_id": "e1",
            "predicate": "unsupported_link",
            "obj_entity_id": "e2",
            "doc_id": "d",
            "segment_id": "s",
            "confidence": 0.7,
        }
    ]
    entity_types = {"e1": "Entity", "e2": "Entity"}
    out = validate_relations(relations, entity_types=entity_types, rules=rules)
    assert out["summary"]["invalid"] == 1
    assert "predicate_not_in_ontology" in str(out["invalid_relations"][0].get("_validation_error"))


def test_validate_relations_rejects_domain_range_mismatch():
    rules = canonical_default_rules()
    relations = [
        {
            "rel_id": "r1",
            "subj_entity_id": "e1",
            "predicate": "has_topic",
            "obj_entity_id": "e2",
            "doc_id": "d",
            "segment_id": "s",
            "confidence": 0.7,
        }
    ]
    entity_types = {"e1": "Person", "e2": "Topic"}
    out = validate_relations(relations, entity_types=entity_types, rules=rules)
    assert out["summary"]["invalid"] == 1
    assert "domain_range_mismatch" in str(out["invalid_relations"][0].get("_validation_error"))
