"""Graph retrieval (MVP) using Snowflake graph tables."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from app.clients.snowflake_client import SnowflakeClient
from app.core.storage import artifact_root


def _sql_in(values: List[str]) -> str:
    escaped = [v.replace("'", "''") for v in values]
    return ", ".join([f"'{v}'" for v in escaped])


def _query_entities_by_name(client: SnowflakeClient, query: str, limit: int) -> List[Dict[str, Any]]:
    q = query.replace("'", "''")
    sql = (
        "SELECT ENTITY_ID, NAME, TYPE FROM ENTITIES "
        f"WHERE NAME ILIKE '%{q}%' LIMIT {limit}"
    )
    return client.execute_query(sql)


def _query_relations(client: SnowflakeClient, entity_ids: List[str], limit: int) -> List[Dict[str, Any]]:
    if not entity_ids:
        return []
    in_sql = _sql_in(entity_ids)
    sql = (
        "SELECT REL_ID, SUBJ_ENTITY_ID, PREDICATE, OBJ_ENTITY_ID, DOC_ID, SEGMENT_ID, CONFIDENCE "
        "FROM RELATIONS "
        f"WHERE SUBJ_ENTITY_ID IN ({in_sql}) LIMIT {limit}"
    )
    return client.execute_query(sql)


def _query_entities_by_ids(client: SnowflakeClient, entity_ids: List[str], limit: int) -> List[Dict[str, Any]]:
    if not entity_ids:
        return []
    in_sql = _sql_in(entity_ids)
    sql = (
        "SELECT ENTITY_ID, NAME, TYPE FROM ENTITIES "
        f"WHERE ENTITY_ID IN ({in_sql}) LIMIT {limit}"
    )
    return client.execute_query(sql)


def retrieve(query: str, limit: int = 10, hops: int = 1, client: Optional[SnowflakeClient] = None) -> List[Dict[str, Any]]:
    client = client or SnowflakeClient()
    if hasattr(client, "execute_query"):
        try:
            seed_entities = _query_entities_by_name(client, query, limit=limit)
            seed_ids = [e.get("entity_id") for e in seed_entities if e.get("entity_id")]
            all_entities = {e.get("entity_id"): e for e in seed_entities if e.get("entity_id")}
            all_relations: List[Dict[str, Any]] = []

            frontier: Set[str] = set(seed_ids)
            for _ in range(max(0, hops)):
                if not frontier:
                    break
                relations = _query_relations(client, list(frontier), limit=limit * 5)
                all_relations.extend(relations)
                next_ids = {r.get("obj_entity_id") for r in relations if r.get("obj_entity_id")}
                next_ids = {i for i in next_ids if i and i not in all_entities}
                if not next_ids:
                    break
                new_entities = _query_entities_by_ids(client, list(next_ids), limit=limit * 5)
                for e in new_entities:
                    if e.get("entity_id"):
                        all_entities[e.get("entity_id")] = e
                frontier = {e.get("entity_id") for e in new_entities if e.get("entity_id")}

            if seed_entities or all_relations:
                return [
                    {
                        "entities": list(all_entities.values()),
                        "relations": all_relations,
                    }
                ]
        except Exception:
            pass

    local_entities, local_relations = _retrieve_local(query, limit=limit, hops=hops)
    if not local_entities and not local_relations:
        return [{"entity_id": "N/A", "name": query, "sql": "no results"}]
    return [{"entities": local_entities, "relations": local_relations}]


def _load_local_graph() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    entities: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    root = artifact_root()
    for ent_file in root.rglob("graph/entities.jsonl"):
        try:
            for line in ent_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entities.append(json.loads(line))
        except Exception:
            continue
    for rel_file in root.rglob("graph/relations.jsonl"):
        try:
            for line in rel_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                relations.append(json.loads(line))
        except Exception:
            continue
    return entities, relations


def _retrieve_local(query: str, limit: int, hops: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    entities, relations = _load_local_graph()
    if not entities:
        return [], []
    q = query.lower()
    seed_entities = [e for e in entities if q in str(e.get("name", "")).lower()]
    seed_entities = seed_entities[:limit]
    all_entities = {e.get("entity_id"): e for e in seed_entities if e.get("entity_id")}
    all_relations: List[Dict[str, Any]] = []

    frontier: Set[str] = {e.get("entity_id") for e in seed_entities if e.get("entity_id")}
    for _ in range(max(0, hops)):
        if not frontier:
            break
        step_relations = [r for r in relations if r.get("subj_entity_id") in frontier]
        all_relations.extend(step_relations)
        next_ids = {r.get("obj_entity_id") for r in step_relations if r.get("obj_entity_id")}
        next_ids = {i for i in next_ids if i and i not in all_entities}
        if not next_ids:
            break
        for e in entities:
            eid = e.get("entity_id")
            if eid in next_ids:
                all_entities[eid] = e
        frontier = next_ids

    return list(all_entities.values()), all_relations
