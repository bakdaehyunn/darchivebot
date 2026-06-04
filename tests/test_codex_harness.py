from __future__ import annotations

import json

import pytest

from darchivebot.codex_harness import PROMPT, ensure_capture_schema, validate_codex_item


def test_ensure_capture_schema_writes_required_schema(tmp_path):
    path = ensure_capture_schema(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "capture_id" in payload["required"]
    assert "core_summary" in payload["required"]
    assert "key_points" in payload["required"]
    assert "raw_extracted_text" in payload["required"]
    assert "why_saved" in payload["required"]
    assert payload["additionalProperties"] is False


def test_prompt_requires_screenshot_core_extraction_without_sqlite_writes():
    assert "screenshots/photos as the primary input" in PROMPT
    assert "actual core meaning inside the image" in PROMPT
    assert "Do not modify files or write to SQLite" in PROMPT
    assert "Python will validate your JSON and write SQLite" in PROMPT


def test_validate_codex_item_rejects_mismatched_capture_id():
    with pytest.raises(ValueError):
        validate_codex_item(
            {
                "capture_id": "other",
                "title": "title",
                "core_summary": "",
                "key_points": [],
                "context": "",
                "raw_extracted_text": "",
                "why_saved": "",
                "source_language": "unknown",
                "content_type": "text",
                "tags": [],
                "dates_mentioned": [],
                "people_mentioned": [],
                "action_candidates": [],
                "confidence": 0,
                "needs_review": True,
            },
            "capture",
        )


def test_validate_codex_item_normalizes_new_fields_with_old_fallbacks():
    item = validate_codex_item(
        {
            "capture_id": "capture",
            "title": " title ",
            "summary": "old summary",
            "extracted_text": "old text",
            "source_language": "ko",
            "content_type": "photo",
            "tags": [" capture "],
            "dates_mentioned": [],
            "people_mentioned": [],
            "action_candidates": [],
            "confidence": 2,
            "needs_review": False,
        },
        "capture",
    )

    assert item["core_summary"] == "old summary"
    assert item["raw_extracted_text"] == "old text"
    assert item["summary"] == "old summary"
    assert item["extracted_text"] == "old text"
    assert item["key_points"] == []
    assert item["confidence"] == 1.0
