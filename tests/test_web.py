from __future__ import annotations

import pytest

from darchivebot.storage import ArchiveStore
from darchivebot.web import render_capture_detail, render_home, render_review, render_search, serve_local_web


def test_web_pages_render_search_review_and_detail(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:web",
        chat_id="chat",
        message_id=1,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="SQLite local archive",
        caption="",
        content_kind="text",
        raw_message={"message_id": 1},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "SQLite archive retrieval",
            "core_summary": "Search makes saved captures reusable.",
            "key_points": ["FTS before embeddings"],
            "raw_extracted_text": "SQLite FTS supports local archive retrieval.",
            "source_language": "en",
            "tags": ["search", "sqlite"],
            "primary_interest": "AI",
            "secondary_interests": ["product"],
            "topic": "retrieval",
            "revisit_priority": "high",
            "revisit_reason": "daily use",
            "insight_seed": "local archive search layer",
            "questions": ["What should be retrieved later?"],
            "confidence": 0.9,
            "needs_review": False,
        },
    )

    assert "SQLite archive retrieval" in render_home(store)
    assert "Matched" in render_search(store, {"q": ["SQLite"]})
    assert "Review queue" in render_review(store, {"mode": ["revisit"]})
    detail = render_capture_detail(store, capture_id)
    assert "Extracted text" in detail
    assert "local archive search layer" in detail
    assert "What should be retrieved later?" in detail


def test_web_server_rejects_non_local_host(tmp_path):
    store = ArchiveStore(tmp_path / "state")

    with pytest.raises(ValueError):
        serve_local_web(store, host="0.0.0.0", port=8765)
