from __future__ import annotations

from darchivebot.storage import ArchiveStore


def test_add_capture_is_idempotent(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    first = store.add_capture(
        capture_key="chat:1",
        chat_id="chat",
        message_id=1,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=1_700_000_000,
        text="hello",
        caption="",
        content_kind="text",
        raw_message={"message_id": 1},
    )
    second = store.add_capture(
        capture_key="chat:1",
        chat_id="chat",
        message_id=1,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=1_700_000_000,
        text="hello again",
        caption="",
        content_kind="text",
        raw_message={"message_id": 1},
    )

    assert first == second
    rows = store.list_captures(10)
    assert len(rows) == 1
    assert rows[0]["text"] == "hello"


def test_archive_item_upsert_and_status(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:2",
        chat_id="chat",
        message_id=2,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="오늘 읽을 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 2},
    )

    store.upsert_extracted_text(capture_id=capture_id, source="codex", text="오늘 읽을 글")
    store.upsert_archive_item(
        capture_id,
        {
            "title": "읽을 글",
            "summary": "관심 글",
            "extracted_text": "오늘 읽을 글",
            "source_language": "ko",
            "tags": ["reading"],
            "dates_mentioned": [],
            "people_mentioned": [],
            "action_candidates": [],
            "confidence": 0.9,
            "needs_review": False,
        },
    )
    store.mark_capture_status(capture_id, "processed")

    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "processed"
    with store.connect() as conn:
        archive_count = conn.execute("SELECT COUNT(*) FROM archive_items").fetchone()[0]
        text_count = conn.execute("SELECT COUNT(*) FROM extracted_texts").fetchone()[0]
    assert archive_count == 1
    assert text_count == 1
