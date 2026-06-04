from __future__ import annotations

import json

import pytest

from darchivebot.codex_harness import ensure_capture_schema, validate_codex_item


def test_ensure_capture_schema_writes_required_schema(tmp_path):
    path = ensure_capture_schema(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "capture_id" in payload["required"]
    assert payload["additionalProperties"] is False


def test_validate_codex_item_rejects_mismatched_capture_id():
    with pytest.raises(ValueError):
        validate_codex_item(
            {
                "capture_id": "other",
                "title": "title",
                "summary": "",
                "extracted_text": "",
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
