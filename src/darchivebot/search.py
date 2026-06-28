from __future__ import annotations

import json
import re
from typing import Any

from darchivebot.readiness import related_captures
from darchivebot.storage import ArchiveStore


SEARCH_FIELDS = [
    ("title", "search_title"),
    ("summary", "search_summary"),
    ("extracted_text", "search_extracted_text"),
    ("tags", "search_tags"),
    ("interests", "search_interests"),
    ("topics", "search_topics"),
    ("questions", "search_questions"),
    ("insight_seed", "search_insight_seed"),
    ("source_text", "search_source_text"),
]


def rebuild_search_index(store: ArchiveStore) -> dict[str, Any]:
    return store.rebuild_search_index()


def search_archive(store: ArchiveStore, query: str, *, limit: int = 20) -> dict[str, Any]:
    rows = store.search_archive(format_fts_query(query), limit=limit)
    return {
        "query": query,
        "count": len(rows),
        "results": [search_result(row, query) for row in rows],
    }


def review_queue(
    store: ArchiveStore,
    *,
    limit: int = 20,
    needs_review_only: bool = False,
    revisit_only: bool = False,
) -> dict[str, Any]:
    rows = store.review_archive_items(
        limit=limit,
        needs_review_only=needs_review_only,
        revisit_only=revisit_only,
    )
    mode = "needs-review" if needs_review_only else "revisit" if revisit_only else "all"
    return {"mode": mode, "count": len(rows), "items": [archive_item_summary(row) for row in rows]}


def archive_detail(store: ArchiveStore, capture_id: str, *, related_limit: int = 6) -> dict[str, Any] | None:
    capture = store.get_capture(capture_id)
    if capture is None:
        return None
    files = store.files_for_capture(capture_id)
    archive = store.get_archive_item(capture_id)
    related = related_captures(store, capture_id, limit=related_limit) if archive is not None else None
    return {
        "capture": row_to_dict(capture),
        "files": [row_to_dict(file_row) for file_row in files],
        "archive_item": archive_item_to_dict(archive) if archive is not None else None,
        "related": related["related"] if related else [],
    }


def search_result(row: Any, query: str) -> dict[str, Any]:
    item = archive_item_summary(row)
    item["rank"] = float(row["search_rank"] or 0.0)
    item["snippet"] = clean_snippet(row["search_snippet"])
    item["matched_fields"] = matched_fields(row, query)
    item["match_explanation"] = match_explanation(item["matched_fields"])
    return item


def archive_item_summary(row: Any) -> dict[str, Any]:
    return {
        "capture_id": str(row["capture_id"]),
        "archive_item_id": str(row["id"]),
        "title": str(row["title"] or ""),
        "summary": str(row["core_summary"] or row["summary"] or ""),
        "primary_interest": str(row["primary_interest"] or ""),
        "secondary_interests": json_list(row["secondary_interests_json"]),
        "topic": str(row["topic"] or ""),
        "subtopic": str(row["subtopic"] or ""),
        "tags": json_list(row["tags_json"]),
        "questions": json_list(row["questions_json"]),
        "revisit_priority": str(row["revisit_priority"] or ""),
        "revisit_reason": str(row["revisit_reason"] or ""),
        "insight_seed": str(row["insight_seed"] or ""),
        "needs_review": bool(row["needs_review"]),
        "confidence": float(row["confidence"] or 0.0),
        "content_kind": str(row["content_kind"] or ""),
        "capture_status": str(row["capture_status"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def archive_item_to_dict(row: Any) -> dict[str, Any]:
    data = row_to_dict(row)
    data["core_summary"] = data.get("core_summary") or data.get("summary") or ""
    data["raw_extracted_text"] = data.get("raw_extracted_text") or data.get("extracted_text") or ""
    data["key_points"] = json_list(data.get("key_points_json"))
    data["tags"] = json_list(data.get("tags_json"))
    data["secondary_interests"] = json_list(data.get("secondary_interests_json"))
    data["questions"] = json_list(data.get("questions_json"))
    data["relation_candidates"] = json_list(data.get("relation_candidates_json"))
    data["dates_mentioned"] = json_list(data.get("dates_mentioned_json"))
    data["people_mentioned"] = json_list(data.get("people_mentioned_json"))
    data["action_candidates"] = json_list(data.get("action_candidates_json"))
    data["needs_review"] = bool(data.get("needs_review"))
    return data


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def matched_fields(row: Any, query: str) -> list[str]:
    tokens = query_tokens(query)
    if not tokens:
        return []
    matches: list[str] = []
    for label, key in SEARCH_FIELDS:
        haystack = str(row[key] or "").lower()
        if any(token in haystack for token in tokens):
            matches.append(label)
    return matches


def match_explanation(fields: list[str]) -> str:
    if not fields:
        return "Matched the local FTS index."
    return "Matched " + ", ".join(fields) + "."


def format_fts_query(query: str) -> str:
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    if not terms:
        return ""
    return " ".join(f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms)


def query_tokens(query: str) -> list[str]:
    return [term.lower() for term in re.split(r"\s+", query.strip()) if term.strip()]


def clean_snippet(value: Any) -> str:
    return str(value or "").replace("\n", " ").strip()


def json_list(value: Any) -> list[str]:
    try:
        payload = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if str(item).strip()]
