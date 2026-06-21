from __future__ import annotations

import json
from collections import Counter
from typing import Any

from darchivebot.storage import ArchiveStore


ISSUE_SPECS = [
    (
        "missing_primary_interest",
        "missing primary interest",
        lambda row: not clean(row["primary_interest"]),
    ),
    (
        "unknown_primary_interest",
        "primary interest is other/unknown",
        lambda row: clean(row["primary_interest"]).lower() == "other/unknown",
    ),
    ("missing_topic", "missing topic", lambda row: not clean(row["topic"])),
    ("missing_insight_seed", "missing insight seed", lambda row: not clean(row["insight_seed"])),
    ("missing_key_points", "missing key points", lambda row: not json_list(row["key_points_json"])),
    ("missing_concepts", "missing concepts", lambda row: not json_list(row["tags_json"])),
    ("needs_review", "needs review", lambda row: bool(row["needs_review"])),
    ("low_confidence", "low confidence", lambda row: confidence(row) < 0.5),
    ("fallback_processed", "fallback processed", lambda row: is_fallback_processed(row)),
    ("missing_questions", "missing questions", lambda row: not semantic_json_list(row, "questions_json", "questions")),
    (
        "missing_relation_candidates",
        "missing relation candidates",
        lambda row: not semantic_json_list(row, "relation_candidates_json", "relation_candidates"),
    ),
]
ISSUE_NAMES = [name for name, _label, _predicate in ISSUE_SPECS]


def interest_summary(store: ArchiveStore, *, limit: int = 20) -> dict[str, Any]:
    rows = store.list_archive_items_for_graph()
    primary = Counter[str]()
    secondary = Counter[str]()
    for row in rows:
        primary_interest = clean(row["primary_interest"])
        if primary_interest:
            primary[primary_interest] += 1
        for item in json_list(row["secondary_interests_json"]):
            secondary[item] += 1
    names = sorted(set(primary) | set(secondary), key=lambda item: (-(primary[item] + secondary[item]), item))
    interests = [
        {
            "interest": name,
            "primary_count": primary[name],
            "secondary_count": secondary[name],
            "total_count": primary[name] + secondary[name],
        }
        for name in names[:limit]
    ]
    return {"archive_items": len(rows), "interests": interests}


def concept_summary(store: ArchiveStore, *, limit: int = 20) -> dict[str, Any]:
    rows = store.list_archive_items_for_graph()
    counts = Counter[str]()
    for row in rows:
        counts.update(json_list(row["tags_json"]))
    concepts = [
        {"concept": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]
    return {"archive_items": len(rows), "concepts": concepts}


def graph_quality_summary(store: ArchiveStore, *, limit: int = 20) -> dict[str, Any]:
    rows = store.list_archive_items_for_graph()
    issues = []
    for name, _label, predicate in ISSUE_SPECS:
        matches = [row for row in rows if predicate(row)]
        issues.append(
            {
                "name": name,
                "count": len(matches),
                "items": [quality_item(row) for row in matches[:limit]],
            }
        )
    blocking_names = {"missing_primary_interest", "unknown_primary_interest", "fallback_processed", "missing_topic"}
    blocking_count = sum(issue["count"] for issue in issues if issue["name"] in blocking_names)
    return {
        "archive_items": len(rows),
        "ready_for_synthesis": bool(rows) and blocking_count == 0,
        "issues": issues,
        "next_step": "Improve archive classification before insight synthesis" if blocking_count else "Archive is ready for related-capture experiments",
    }


def reprocess_plan(
    store: ArchiveStore,
    *,
    limit: int = 20,
    issue: str = "",
    fallback_only: bool = False,
    needs_review_only: bool = False,
    capture_id: str = "",
) -> dict[str, Any]:
    rows = store.list_archive_items_for_graph()
    requested_limit = max(0, limit)
    histories = store.processing_runs_for_capture_ids([str(row["capture_id"]) for row in rows])
    candidates = []
    for row in rows:
        reasons = candidate_reasons(row)
        if not reasons:
            continue
        reason_names = {item["name"] for item in reasons}
        if issue and issue not in reason_names:
            continue
        if fallback_only and "fallback_processed" not in reason_names:
            continue
        if needs_review_only and "needs_review" not in reason_names:
            continue
        if capture_id and capture_id not in {str(row["capture_id"]), str(row["id"])}:
            continue
        candidates.append(reprocess_candidate(row, reasons, histories.get(str(row["capture_id"]), [])))
    return {
        "filters": {
            "issue": issue,
            "fallback_only": fallback_only,
            "needs_review_only": needs_review_only,
            "capture_id": capture_id,
            "limit": requested_limit,
        },
        "candidate_count": len(candidates),
        "candidates": candidates[:requested_limit],
        "available_issues": ISSUE_NAMES,
        "next_step": "Select capture ids explicitly before running any non-dry-run reprocessing.",
    }


def reprocess_candidate(row: Any, reasons: list[dict[str, str]], history: list[Any]) -> dict[str, Any]:
    visible_history = history[:5]
    return {
        "capture_id": str(row["capture_id"]),
        "archive_item_id": str(row["id"]),
        "title": clean(row["title"]) or "Untitled capture",
        "content_kind": clean(row["content_kind"]),
        "current": {
            "primary_interest": clean(row["primary_interest"]),
            "topic": clean(row["topic"]),
            "confidence": confidence(row),
            "needs_review": bool(row["needs_review"]),
        },
        "candidate_reasons": reasons,
        "processor_history_count": len(history),
        "processor_history": [
            {
                "processor": clean(item["processor"]),
                "status": clean(item["status"]),
                "started_at": clean(item["started_at"]),
                "finished_at": clean(item["finished_at"]),
                "error": clean(item["error"]),
            }
            for item in visible_history
        ],
    }


def candidate_reasons(row: Any) -> list[dict[str, str]]:
    return [
        {"name": name, "label": label}
        for name, label, predicate in ISSUE_SPECS
        if predicate(row)
    ]


def related_captures(store: ArchiveStore, capture_id: str, *, limit: int = 10) -> dict[str, Any] | None:
    rows = store.list_archive_items_for_graph()
    target = next((row for row in rows if str(row["capture_id"]) == capture_id or str(row["id"]) == capture_id), None)
    if target is None:
        return None
    matches = []
    for row in rows:
        if str(row["id"]) == str(target["id"]):
            continue
        match = related_match(target, row)
        if match["score"] > 0:
            matches.append(match)
    matches.sort(key=lambda item: (-item["score"], item["title"], item["capture_id"]))
    return {"capture_id": str(target["capture_id"]), "archive_item_id": str(target["id"]), "related": matches[:limit]}


def related_match(source: Any, candidate: Any) -> dict[str, Any]:
    source_interests = interest_set(source)
    candidate_interests = interest_set(candidate)
    source_topics = topic_set(source)
    candidate_topics = topic_set(candidate)
    source_concepts = set(json_list(source["tags_json"]))
    candidate_concepts = set(json_list(candidate["tags_json"]))
    shared_interests = sorted(source_interests & candidate_interests)
    shared_topics = sorted(source_topics & candidate_topics)
    shared_concepts = sorted(source_concepts & candidate_concepts)
    score = 0
    reasons = []
    if shared_topics:
        score += 3 * len(shared_topics)
        reasons.append(f"shared topics: {', '.join(shared_topics)}")
    if shared_interests:
        score += 2 * len(shared_interests)
        reasons.append(f"shared interests: {', '.join(shared_interests)}")
    if shared_concepts:
        score += len(shared_concepts)
        reasons.append(f"shared concepts: {', '.join(shared_concepts)}")
    source_relation_candidates = set(semantic_json_list(source, "relation_candidates_json", "relation_candidates"))
    candidate_relation_candidates = set(semantic_json_list(candidate, "relation_candidates_json", "relation_candidates"))
    shared_relation_candidates = sorted(source_relation_candidates & candidate_relation_candidates)
    if shared_relation_candidates:
        score += 2 * len(shared_relation_candidates)
        reasons.append(f"shared relation candidates: {', '.join(shared_relation_candidates)}")
    return {
        "capture_id": str(candidate["capture_id"]),
        "archive_item_id": str(candidate["id"]),
        "title": clean(candidate["title"]) or "Untitled capture",
        "score": score,
        "reasons": reasons,
        "shared_interests": shared_interests,
        "shared_topics": shared_topics,
        "shared_concepts": shared_concepts,
    }


def interest_set(row: Any) -> set[str]:
    values = set(json_list(row["secondary_interests_json"]))
    primary = clean(row["primary_interest"])
    if primary:
        values.add(primary)
    return values


def topic_set(row: Any) -> set[str]:
    return {value for value in (clean(row["topic"]), clean(row["subtopic"])) if value}


def quality_item(row: Any) -> dict[str, str]:
    return {
        "capture_id": str(row["capture_id"]),
        "archive_item_id": str(row["id"]),
        "title": clean(row["title"]) or "Untitled capture",
    }


def is_fallback_processed(row: Any) -> bool:
    return "local fallback" in clean(row["classification_reason"]).lower()


def confidence(row: Any) -> float:
    try:
        return float(row["confidence"] or 0.0)
    except (TypeError, ValueError):
        return 0.0


def raw_json_list(row: Any, key: str) -> list[str]:
    try:
        payload = json.loads(str(row["raw_codex_json"] or "{}"))
    except json.JSONDecodeError:
        return []
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [clean(item) for item in value if clean(item)]


def semantic_json_list(row: Any, column: str, raw_key: str) -> list[str]:
    if column in row.keys():
        normalized = json_list(row[column])
        if normalized:
            return normalized
    return raw_json_list(row, raw_key)


def json_list(value: Any) -> list[str]:
    try:
        payload = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [clean(item) for item in payload if clean(item)]


def clean(value: Any) -> str:
    return str(value or "").strip()
