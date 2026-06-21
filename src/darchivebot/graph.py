from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darchivebot.json_utils import dumps
from darchivebot.storage import ArchiveStore


ONTOLOGY_VERSION = "2026-06-08"
GRAPH_EXPORT_VERSION = 1

GRAPH_CONTEXT: dict[str, Any] = {
    "darch": "https://darchivebot.local/ontology#",
    "schema": "https://schema.org/",
    "id": "@id",
    "type": "@type",
    "title": "schema:name",
    "summary": "schema:description",
    "createdAt": "schema:dateCreated",
    "updatedAt": "schema:dateModified",
    "aboutCapture": {"@id": "darch:aboutCapture", "@type": "@id"},
    "hasInterest": {"@id": "darch:hasInterest", "@type": "@id"},
    "hasSecondaryInterest": {"@id": "darch:hasSecondaryInterest", "@type": "@id"},
    "hasTopic": {"@id": "darch:hasTopic", "@type": "@id"},
    "hasSubtopic": {"@id": "darch:hasSubtopic", "@type": "@id"},
    "mentionsConcept": {"@id": "darch:mentionsConcept", "@type": "@id"},
    "makesClaim": {"@id": "darch:makesClaim", "@type": "@id"},
    "asksQuestion": {"@id": "darch:asksQuestion", "@type": "@id"},
    "hasRelationCandidate": {"@id": "darch:hasRelationCandidate", "@type": "@id"},
}


def default_graph_path(root: Path) -> Path:
    return root / ".local" / "graph" / "darchivebot.jsonld"


def export_graph(
    store: ArchiveStore,
    output_path: Path,
    *,
    limit: int | None = None,
    include_raw_text: bool = False,
) -> dict[str, Any]:
    rows = store.list_archive_items_for_graph(limit=limit)
    payload = build_graph_document(rows, include_raw_text=include_raw_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dumps(payload) + "\n", encoding="utf-8")
    metadata = dict(payload["metadata"])
    metadata["path"] = str(output_path)
    return metadata


def build_graph_document(rows: list[Any], *, include_raw_text: bool = False) -> dict[str, Any]:
    graph: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    for row in rows:
        for node in graph_nodes_for_archive_row(row, include_raw_text=include_raw_text):
            node_id = str(node.get("@id") or "")
            if node_id and node_id in seen_node_ids:
                continue
            if node_id:
                seen_node_ids.add(node_id)
            graph.append(node)
    metadata = {
        "@type": "darch:GraphExport",
        "ontology_version": ONTOLOGY_VERSION,
        "export_version": GRAPH_EXPORT_VERSION,
        "export_scope": "lightweight_jsonld",
        "source": "sqlite_archive_rows",
        "semantic_store_equivalent": False,
        "generated_at": utc_now(),
        "archive_items": len(rows),
        "nodes": len(graph),
        "raw_text_included": include_raw_text,
    }
    return {"@context": GRAPH_CONTEXT, "metadata": metadata, "@graph": graph}


def graph_nodes_for_archive_row(row: Any, *, include_raw_text: bool = False) -> list[dict[str, Any]]:
    archive_id = str(row["id"])
    capture_id = str(row["capture_id"])
    archive_node_id = urn("archive-item", archive_id)
    capture_node_id = urn("capture", capture_id)
    key_points = json_list(row["key_points_json"])
    tags = json_list(row["tags_json"])
    secondary_interests = json_list(row["secondary_interests_json"])
    questions = semantic_json_list(row, "questions_json", "questions")
    relation_candidates = semantic_json_list(row, "relation_candidates_json", "relation_candidates")
    primary_interest = str(row["primary_interest"] or "").strip()
    topic = str(row["topic"] or "").strip()
    subtopic = str(row["subtopic"] or "").strip()

    archive_node: dict[str, Any] = compact_dict(
        {
            "@id": archive_node_id,
            "@type": "darch:ArchiveItem",
            "title": str(row["title"] or ""),
            "summary": str(row["core_summary"] or row["summary"] or ""),
            "darch:whySaved": str(row["why_saved"] or ""),
            "darch:classificationReason": str(row["classification_reason"] or ""),
            "darch:revisitPriority": str(row["revisit_priority"] or ""),
            "darch:revisitReason": str(row["revisit_reason"] or ""),
            "darch:insightSeed": str(row["insight_seed"] or ""),
            "darch:sourceLanguage": str(row["source_language"] or ""),
            "darch:confidence": float(row["confidence"] or 0.0),
            "darch:needsReview": bool(row["needs_review"]),
            "aboutCapture": capture_node_id,
            "hasInterest": interest_id(primary_interest) if primary_interest else "",
            "hasSecondaryInterest": [interest_id(item) for item in secondary_interests],
            "hasTopic": topic_id(topic) if topic else "",
            "hasSubtopic": topic_id(subtopic) if subtopic else "",
            "mentionsConcept": [concept_id(item) for item in tags],
            "makesClaim": [claim_id(archive_id, index) for index, _ in enumerate(key_points, start=1)],
            "asksQuestion": [question_id(item) for item in questions],
            "hasRelationCandidate": [relation_candidate_id(archive_id, item) for item in relation_candidates],
            "updatedAt": str(row["updated_at"] or ""),
        }
    )
    if include_raw_text:
        raw_text = str(row["raw_extracted_text"] or row["extracted_text"] or "")
        if raw_text:
            archive_node["darch:rawExtractedText"] = raw_text
    capture_node = compact_dict(
        {
            "@id": capture_node_id,
            "@type": "darch:Capture",
            "darch:captureKey": str(row["capture_key"] or ""),
            "darch:messageId": int(row["message_id"] or 0),
            "darch:contentKind": str(row["content_kind"] or ""),
            "darch:messageDatetime": str(row["message_datetime"] or ""),
        }
    )

    nodes = [capture_node, archive_node]
    if primary_interest:
        nodes.append(named_node(interest_id(primary_interest), "darch:Interest", primary_interest))
    for item in secondary_interests:
        nodes.append(named_node(interest_id(item), "darch:Interest", item))
    if topic:
        nodes.append(named_node(topic_id(topic), "darch:Topic", topic))
    if subtopic:
        nodes.append(named_node(topic_id(subtopic), "darch:Topic", subtopic))
    for tag in tags:
        nodes.append(named_node(concept_id(tag), "darch:Concept", tag))
    for index, point in enumerate(key_points, start=1):
        nodes.append(
            compact_dict(
                {
                    "@id": claim_id(archive_id, index),
                    "@type": "darch:Claim",
                    "summary": point,
                    "darch:claimOrder": index,
                    "darch:fromArchiveItem": archive_node_id,
                }
            )
        )
    for question in questions:
        nodes.append(named_node(question_id(question), "darch:Question", question))
    for candidate in relation_candidates:
        nodes.append(named_node(relation_candidate_id(archive_id, candidate), "darch:RelationCandidate", candidate))
    return nodes


def named_node(node_id: str, node_type: str, name: str) -> dict[str, Any]:
    return {"@id": node_id, "@type": node_type, "title": name}


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


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if item == "" or item == [] or item is None:
            continue
        result[key] = item
    return result


def interest_id(value: str) -> str:
    return urn("interest", slugify(value or "other-unknown"))


def topic_id(value: str) -> str:
    return urn("topic", slugify(value))


def concept_id(value: str) -> str:
    return urn("concept", slugify(value))


def claim_id(archive_id: str, index: int) -> str:
    return urn("claim", f"{archive_id}-{index}")


def question_id(value: str) -> str:
    return urn("question", stable_hash(value))


def relation_candidate_id(archive_id: str, value: str) -> str:
    return urn("relation-candidate", stable_hash(f"{archive_id}:{value}"))


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:16]


def urn(kind: str, value: str) -> str:
    return f"urn:darchive:{kind}:{value}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣._/-]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
