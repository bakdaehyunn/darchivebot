from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pyoxigraph import Literal, NamedNode, Quad, RdfFormat, Store

from darchivebot.graph import GRAPH_EXPORT_VERSION, ONTOLOGY_VERSION, claim_id, concept_id, interest_id, topic_id, urn
from darchivebot.storage import ArchiveStore


DARCH = "https://darchivebot.local/ontology#"
SCHEMA = "https://schema.org/"
RDF_TYPE = NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
XSD_BOOLEAN = NamedNode("http://www.w3.org/2001/XMLSchema#boolean")
XSD_DATE_TIME = NamedNode("http://www.w3.org/2001/XMLSchema#dateTime")
XSD_DECIMAL = NamedNode("http://www.w3.org/2001/XMLSchema#decimal")
XSD_INTEGER = NamedNode("http://www.w3.org/2001/XMLSchema#integer")
SEMANTIC_GRAPH_NAME = NamedNode("https://darchivebot.local/graph/semantic")


def default_semantic_store_path(root: Path) -> Path:
    return root / ".local" / "graph" / "semantic-store"


def default_semantic_export_path(root: Path) -> Path:
    return root / ".local" / "graph" / "semantic-store.nq"


def init_semantic_store(path: Path) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    store = Store(path)
    store.add_graph(SEMANTIC_GRAPH_NAME)
    store.flush()
    return semantic_store_stats_from_store(store, path)


def sync_semantic_store(
    archive_store: ArchiveStore,
    path: Path,
    *,
    include_raw_text: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    rows = archive_store.list_archive_items_for_graph(limit=limit)
    path.mkdir(parents=True, exist_ok=True)
    store = Store(path)
    generated_at = utc_now()
    quads = list(quads_for_archive_rows(rows, include_raw_text=include_raw_text))
    quads.extend(metadata_quads(rows=rows, quads_count=len(quads), include_raw_text=include_raw_text, generated_at=generated_at))
    store.clear()
    store.add_graph(SEMANTIC_GRAPH_NAME)
    store.extend(quads)
    store.flush()
    stats = semantic_store_stats_from_store(store, path)
    stats["synced_archive_items"] = len(rows)
    stats["generated_at"] = generated_at
    return stats


def semantic_store_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "quads": 0,
            "archive_items": 0,
            "captures": 0,
            "interests": 0,
            "topics": 0,
            "concepts": 0,
            "claims": 0,
            "questions": 0,
            "relation_candidates": 0,
            "raw_text_included": False,
        }
    store = Store(path)
    return semantic_store_stats_from_store(store, path)


def semantic_store_stats_from_store(store: Store, path: Path) -> dict[str, Any]:
    stats = {
        "path": str(path),
        "exists": True,
        "quads": len(list(store)),
        "archive_items": count_type(store, "ArchiveItem"),
        "captures": count_type(store, "Capture"),
        "interests": count_type(store, "Interest"),
        "topics": count_type(store, "Topic"),
        "concepts": count_type(store, "Concept"),
        "claims": count_type(store, "Claim"),
        "questions": count_type(store, "Question"),
        "relation_candidates": count_type(store, "RelationCandidate"),
        "raw_text_included": bool_query(store, "ASK { GRAPH <https://darchivebot.local/graph/semantic> { ?s <https://darchivebot.local/ontology#rawExtractedText> ?o } }"),
    }
    sync_rows = list(
        store.query(
            """
            SELECT ?generated_at ?ontology_version ?export_version WHERE {
              GRAPH <https://darchivebot.local/graph/semantic> {
                <urn:darchive:graph-sync:current> <https://darchivebot.local/ontology#generatedAt> ?generated_at ;
                  <https://darchivebot.local/ontology#ontologyVersion> ?ontology_version ;
                  <https://darchivebot.local/ontology#exportVersion> ?export_version .
              }
            }
            LIMIT 1
            """
        )
    )
    if sync_rows:
        stats["generated_at"] = sync_rows[0]["generated_at"].value
        stats["ontology_version"] = sync_rows[0]["ontology_version"].value
        stats["export_version"] = int(sync_rows[0]["export_version"].value)
    return stats


def export_semantic_store(path: Path, output_path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"semantic graph store not found: {path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(path)
    store.dump(output_path, format=RdfFormat.N_QUADS)
    result = semantic_store_stats_from_store(store, path)
    result["export_path"] = str(output_path)
    return result


def quads_for_archive_rows(rows: list[Any], *, include_raw_text: bool = False) -> Iterable[Quad]:
    for row in rows:
        yield from quads_for_archive_row(row, include_raw_text=include_raw_text)


def quads_for_archive_row(row: Any, *, include_raw_text: bool = False) -> Iterable[Quad]:
    archive_id = str(row["id"])
    capture_id = str(row["capture_id"])
    archive_node = node(urn("archive-item", archive_id))
    capture_node = node(urn("capture", capture_id))
    key_points = json_list(row["key_points_json"])
    tags = json_list(row["tags_json"])
    secondary_interests = json_list(row["secondary_interests_json"])
    questions = semantic_json_list(row, "questions_json", "questions")
    relation_candidates = semantic_json_list(row, "relation_candidates_json", "relation_candidates")
    primary_interest = str(row["primary_interest"] or "").strip()
    topic = str(row["topic"] or "").strip()
    subtopic = str(row["subtopic"] or "").strip()

    yield q(capture_node, "type", node(f"{DARCH}Capture"), rdf_type=True)
    yield from literal_quads(
        capture_node,
        {
            "captureKey": row["capture_key"],
            "messageId": row["message_id"],
            "contentKind": row["content_kind"],
            "messageDatetime": row["message_datetime"],
        },
    )

    yield q(archive_node, "type", node(f"{DARCH}ArchiveItem"), rdf_type=True)
    yield q(archive_node, "aboutCapture", capture_node)
    yield from literal_quads(
        archive_node,
        {
            "name": row["title"],
            "description": row["core_summary"] or row["summary"],
            "whySaved": row["why_saved"],
            "classificationReason": row["classification_reason"],
            "revisitPriority": row["revisit_priority"],
            "revisitReason": row["revisit_reason"],
            "insightSeed": row["insight_seed"],
            "sourceLanguage": row["source_language"],
            "confidence": row["confidence"],
            "needsReview": bool(row["needs_review"]),
            "dateModified": row["updated_at"],
        },
    )
    if include_raw_text:
        raw_text = str(row["raw_extracted_text"] or row["extracted_text"] or "").strip()
        if raw_text:
            yield q(archive_node, "rawExtractedText", Literal(raw_text))

    if primary_interest:
        interest_node = node(interest_id(primary_interest))
        yield q(archive_node, "hasInterest", interest_node)
        yield from named_resource_quads(interest_node, "Interest", primary_interest)
    for item in secondary_interests:
        interest_node = node(interest_id(item))
        yield q(archive_node, "hasSecondaryInterest", interest_node)
        yield from named_resource_quads(interest_node, "Interest", item)
    if topic:
        topic_node = node(topic_id(topic))
        yield q(archive_node, "hasTopic", topic_node)
        yield from named_resource_quads(topic_node, "Topic", topic)
    if subtopic:
        topic_node = node(topic_id(subtopic))
        yield q(archive_node, "hasSubtopic", topic_node)
        yield from named_resource_quads(topic_node, "Topic", subtopic)
    for tag in tags:
        concept_node = node(concept_id(tag))
        yield q(archive_node, "mentionsConcept", concept_node)
        yield from named_resource_quads(concept_node, "Concept", tag)
    for index, point in enumerate(key_points, start=1):
        claim_node = node(claim_id(archive_id, index))
        yield q(archive_node, "makesClaim", claim_node)
        yield q(claim_node, "type", node(f"{DARCH}Claim"), rdf_type=True)
        yield q(claim_node, "description", Literal(point), schema=True)
        yield q(claim_node, "claimOrder", typed_literal(index))
        yield q(claim_node, "fromArchiveItem", archive_node)
    for question in questions:
        question_node = node(urn("question", stable_hash(question)))
        yield q(archive_node, "asksQuestion", question_node)
        yield from named_resource_quads(question_node, "Question", question)
        yield q(question_node, "fromArchiveItem", archive_node)
    for candidate in relation_candidates:
        relation_node = node(urn("relation-candidate", stable_hash(f"{archive_id}:{candidate}")))
        yield q(archive_node, "hasRelationCandidate", relation_node)
        yield from named_resource_quads(relation_node, "RelationCandidate", candidate)
        yield q(relation_node, "fromArchiveItem", archive_node)


def metadata_quads(*, rows: list[Any], quads_count: int, include_raw_text: bool, generated_at: str) -> list[Quad]:
    sync_node = node("urn:darchive:graph-sync:current")
    values = {
        "ontologyVersion": ONTOLOGY_VERSION,
        "exportVersion": GRAPH_EXPORT_VERSION,
        "generatedAt": generated_at,
        "archiveItems": len(rows),
        "quads": quads_count,
        "rawTextIncluded": include_raw_text,
    }
    return [
        q(sync_node, "type", node(f"{DARCH}GraphStoreSync"), rdf_type=True),
        *literal_quads(sync_node, values),
    ]


def named_resource_quads(subject: NamedNode, class_name: str, title: str) -> Iterable[Quad]:
    yield q(subject, "type", node(f"{DARCH}{class_name}"), rdf_type=True)
    yield q(subject, "name", Literal(title), schema=True)


def literal_quads(subject: NamedNode, values: dict[str, Any]) -> list[Quad]:
    quads = []
    for predicate, value in values.items():
        if value is None or value == "":
            continue
        quads.append(q(subject, predicate, typed_literal(value)))
    return quads


def q(subject: NamedNode, predicate: str, obj: NamedNode | Literal, *, rdf_type: bool = False, schema: bool = False) -> Quad:
    if rdf_type:
        predicate_node = RDF_TYPE
    elif schema:
        predicate_node = node(f"{SCHEMA}{predicate}")
    else:
        predicate_node = node(f"{DARCH}{predicate}")
    return Quad(subject, predicate_node, obj, SEMANTIC_GRAPH_NAME)


def typed_literal(value: Any) -> Literal:
    if isinstance(value, bool):
        return Literal(str(value).lower(), datatype=XSD_BOOLEAN)
    if isinstance(value, int):
        return Literal(str(value), datatype=XSD_INTEGER)
    if isinstance(value, float):
        return Literal(str(value), datatype=XSD_DECIMAL)
    text = str(value).strip()
    if is_iso_datetime(text):
        return Literal(text, datatype=XSD_DATE_TIME)
    return Literal(text)


def node(value: str) -> NamedNode:
    return NamedNode(value)


def count_type(store: Store, class_name: str) -> int:
    return count_query(
        store,
        f"""
        SELECT (COUNT(?s) AS ?count) WHERE {{
          GRAPH <https://darchivebot.local/graph/semantic> {{
            ?s a <https://darchivebot.local/ontology#{class_name}> .
          }}
        }}
        """,
    )


def count_query(store: Store, query: str) -> int:
    rows = list(store.query(query))
    if not rows:
        return 0
    return int(rows[0]["count"].value)


def bool_query(store: Store, query: str) -> bool:
    return bool(store.query(query))


def json_list(value: Any) -> list[str]:
    try:
        payload = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item).strip() for item in payload if str(item).strip()]


def raw_json_list(row: Any, key: str) -> list[str]:
    try:
        payload = json.loads(str(row["raw_codex_json"] or "{}"))
    except json.JSONDecodeError:
        return []
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def semantic_json_list(row: Any, column: str, raw_key: str) -> list[str]:
    if column in row.keys():
        normalized = json_list(row[column])
        if normalized:
            return normalized
    return raw_json_list(row, raw_key)


def stable_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def is_iso_datetime(value: str) -> bool:
    return "T" in value and ("+" in value or value.endswith("Z"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
