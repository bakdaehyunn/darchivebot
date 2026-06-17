from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from darchivebot.readiness import candidate_reasons, related_match
from darchivebot.storage import ArchiveStore


MIN_EVIDENCE_ITEMS = 2
BLOCKING_READINESS_REASONS = {
    "missing_primary_interest",
    "unknown_primary_interest",
    "missing_topic",
    "missing_insight_seed",
    "missing_key_points",
    "missing_concepts",
    "low_confidence",
    "fallback_processed",
}


def generate_insight_note(
    store: ArchiveStore,
    *,
    period: str = "weekly",
    dry_run: bool = False,
    include_needs_review: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    if period != "weekly":
        return {
            "status": "unsupported_period",
            "message": "Only weekly insight notes are supported in the first local implementation.",
            "period_type": period,
        }
    period_start, period_end = weekly_period()
    rows = eligible_archive_rows(
        store.list_archive_items_for_graph(),
        period_start=period_start,
        period_end=period_end,
        include_needs_review=include_needs_review,
    )[: max(0, limit)]
    if len(rows) < MIN_EVIDENCE_ITEMS:
        return {
            "status": "not_enough_evidence",
            "period_type": period,
            "period_start": iso(period_start),
            "period_end": iso(period_end),
            "eligible_count": len(rows),
            "required_count": MIN_EVIDENCE_ITEMS,
            "message": "Not enough processed, review-ready archive items for a useful draft insight note.",
            "next_step": "Process more captures or run `darchive reprocess-plan` to improve archive quality.",
        }

    note = build_local_note(rows, period_start=period_start, period_end=period_end)
    if dry_run:
        return {"status": "dry-run", "would_create": note}
    note_id = store.create_insight_note(note)
    return {"status": "created", "insight_id": note_id, "note": {**note, "id": note_id}}


def list_insight_notes(store: ArchiveStore, *, limit: int = 20) -> dict[str, Any]:
    notes = [insight_note_row(row) for row in store.list_insight_notes(limit)]
    return {"notes": notes, "count": len(notes)}


def show_insight_note(store: ArchiveStore, note_id: str) -> dict[str, Any] | None:
    row = store.get_insight_note(note_id)
    if row is None:
        return None
    note = insight_note_row(row)
    note["recurring_themes"] = load_json(row["recurring_themes_json"])
    note["related_capture_groups"] = load_json(row["related_capture_groups_json"])
    note["notable_archive_item_ids"] = load_json(row["notable_archive_item_ids_json"])
    note["questions"] = load_json(row["questions_json"])
    note["suggested_reviews"] = load_json(row["suggested_reviews_json"])
    note["evidence_items"] = [evidence_row(item) for item in store.insight_note_items(note_id)]
    note["evidence_count"] = len(note["evidence_items"])
    return note


def eligible_archive_rows(
    rows: list[Any],
    *,
    period_start: datetime,
    period_end: datetime,
    include_needs_review: bool,
) -> list[Any]:
    eligible = []
    for row in rows:
        if str(row["capture_status"] or "") != "processed":
            continue
        if bool(row["needs_review"]) and not include_needs_review:
            continue
        if confidence(row) < 0.5:
            continue
        reason_names = {item["name"] for item in candidate_reasons(row)}
        if reason_names & BLOCKING_READINESS_REASONS:
            continue
        timestamp = row_timestamp(row)
        if timestamp is not None and not (period_start <= timestamp <= period_end):
            continue
        eligible.append(row)
    eligible.sort(key=lambda row: str(row["updated_at"] or ""), reverse=True)
    return eligible


def build_local_note(rows: list[Any], *, period_start: datetime, period_end: datetime) -> dict[str, Any]:
    interests = Counter[str]()
    topics = Counter[str]()
    concepts = Counter[str]()
    for row in rows:
        primary_interest = clean(row["primary_interest"])
        if primary_interest:
            interests[primary_interest] += 1
        for item in json_list(row["secondary_interests_json"]):
            interests[item] += 1
        topic = clean(row["topic"])
        if topic:
            topics[topic] += 1
        concepts.update(json_list(row["tags_json"]))

    leading_interest = most_common_name(interests) or "local archive"
    leading_topic = most_common_name(topics)
    title = f"Weekly insight draft: {leading_interest}"
    if leading_topic:
        title += f" / {leading_topic}"

    theme_parts = []
    if interests:
        theme_parts.append(f"interests: {format_counts(interests)}")
    if topics:
        theme_parts.append(f"topics: {format_counts(topics)}")
    if concepts:
        theme_parts.append(f"concepts: {format_counts(concepts)}")
    summary = (
        f"This draft connects {len(rows)} processed archive items from the last week"
        + (f" around {', '.join(theme_parts)}." if theme_parts else ".")
    )

    evidence_ids = [str(row["id"]) for row in rows]
    return {
        "period_type": "weekly",
        "period_start": iso(period_start),
        "period_end": iso(period_end),
        "title": title,
        "summary": summary,
        "recurring_themes": recurring_themes(interests, topics, concepts),
        "related_capture_groups": related_groups(rows),
        "notable_archive_item_ids": evidence_ids,
        "questions": local_questions(rows, leading_interest, leading_topic),
        "suggested_reviews": suggested_reviews(rows),
        "review_status": "draft",
        "confidence": round(min(0.85, 0.5 + (len(rows) * 0.05)), 2),
        "needs_review": True,
        "generator": "local",
        "raw_codex_json": {
            "generator": "local",
            "source": "validated_archive_rows",
            "raw_text_included": False,
            "archive_item_ids": evidence_ids,
        },
    }


def recurring_themes(interests: Counter[str], topics: Counter[str], concepts: Counter[str]) -> list[dict[str, Any]]:
    themes = []
    for name, count in interests.most_common(3):
        themes.append({"type": "interest", "name": name, "evidence_count": count})
    for name, count in topics.most_common(3):
        themes.append({"type": "topic", "name": name, "evidence_count": count})
    for name, count in concepts.most_common(3):
        themes.append({"type": "concept", "name": name, "evidence_count": count})
    return themes


def related_groups(rows: list[Any]) -> list[dict[str, Any]]:
    groups = []
    for index, source in enumerate(rows):
        for candidate in rows[index + 1 :]:
            match = related_match(source, candidate)
            if match["score"] <= 0:
                continue
            groups.append(
                {
                    "archive_item_ids": [str(source["id"]), str(candidate["id"])],
                    "capture_ids": [str(source["capture_id"]), str(candidate["capture_id"])],
                    "score": match["score"],
                    "reasons": match["reasons"],
                }
            )
    groups.sort(key=lambda item: (-int(item["score"]), item["archive_item_ids"]))
    return groups[:5]


def local_questions(rows: list[Any], leading_interest: str, leading_topic: str) -> list[str]:
    questions = []
    if leading_interest and leading_interest != "local archive":
        questions.append(f"What is changing in my saved {leading_interest} material?")
    if leading_topic:
        questions.append(f"Which captures should I revisit around {leading_topic}?")
    for row in rows:
        seed = clean(row["insight_seed"])
        if seed:
            questions.append(f"How does this seed develop: {seed}")
        if len(questions) >= 3:
            break
    return questions[:3]


def suggested_reviews(rows: list[Any]) -> list[dict[str, str]]:
    suggestions = []
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_rows = sorted(
        rows,
        key=lambda row: (priority_order.get(clean(row["revisit_priority"]).lower(), 1), clean(row["title"])),
    )
    for row in sorted_rows[:5]:
        reason = clean(row["revisit_reason"]) or clean(row["insight_seed"]) or clean(row["core_summary"])
        suggestions.append(
            {
                "archive_item_id": str(row["id"]),
                "capture_id": str(row["capture_id"]),
                "title": clean(row["title"]) or "Untitled capture",
                "reason": reason[:240],
            }
        )
    return suggestions


def insight_note_row(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "period_type": str(row["period_type"]),
        "period_start": str(row["period_start"]),
        "period_end": str(row["period_end"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "review_status": str(row["review_status"]),
        "confidence": confidence(row),
        "needs_review": bool(row["needs_review"]),
        "generator": str(row["generator"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "evidence_count": int(row["evidence_count"]) if "evidence_count" in row.keys() else 0,
    }


def evidence_row(row: Any) -> dict[str, Any]:
    return {
        "archive_item_id": str(row["archive_item_id"]),
        "capture_id": str(row["capture_id"]),
        "title": str(row["title"]),
        "core_summary": str(row["core_summary"]),
        "primary_interest": str(row["primary_interest"]),
        "topic": str(row["topic"]),
        "content_kind": str(row["content_kind"]),
        "capture_status": str(row["capture_status"]),
        "evidence_role": str(row["evidence_role"]),
        "evidence_order": int(row["evidence_order"]),
    }


def weekly_period() -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    return start, end


def row_timestamp(row: Any) -> datetime | None:
    for key in ("message_datetime", "updated_at", "created_at"):
        value = clean(row[key])
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def most_common_name(counts: Counter[str]) -> str:
    return counts.most_common(1)[0][0] if counts else ""


def format_counts(counts: Counter[str]) -> str:
    return ", ".join(f"{name} ({count})" for name, count in counts.most_common(3))


def confidence(row: Any) -> float:
    try:
        return float(row["confidence"] or 0.0)
    except (TypeError, ValueError):
        return 0.0


def json_list(value: Any) -> list[str]:
    try:
        payload = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [clean(item) for item in payload if clean(item)]


def load_json(value: Any) -> Any:
    try:
        return json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []


def clean(value: Any) -> str:
    return str(value or "").strip()
