from __future__ import annotations

import sqlite3

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
            "core_summary": "관심 글",
            "key_points": ["나중에 읽기"],
            "context": "text message",
            "raw_extracted_text": "오늘 읽을 글",
            "why_saved": "관심 있는 글",
            "source_language": "ko",
            "tags": ["reading"],
            "primary_interest": "career",
            "secondary_interests": ["AI"],
            "topic": "reading habit",
            "subtopic": "knowledge work",
            "classification_reason": "글 읽기와 업무 성장에 관한 내용",
            "revisit_priority": "high",
            "revisit_reason": "나중에 실행 계획으로 바꿀 수 있음",
            "insight_seed": "읽기 습관과 커리어 성장 연결",
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
        archive = conn.execute("SELECT * FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()
    assert archive_count == 1
    assert text_count == 1
    assert archive["summary"] == "관심 글"
    assert archive["core_summary"] == "관심 글"
    assert archive["extracted_text"] == "오늘 읽을 글"
    assert archive["raw_extracted_text"] == "오늘 읽을 글"
    assert "나중에 읽기" in archive["key_points_json"]
    assert archive["primary_interest"] == "career"
    assert "AI" in archive["secondary_interests_json"]
    assert archive["topic"] == "reading habit"
    assert archive["revisit_priority"] == "high"
    assert archive["insight_seed"] == "읽기 습관과 커리어 성장 연결"


def test_init_db_adds_structured_archive_columns_to_existing_db(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            """
            CREATE TABLE archive_items (
              id TEXT PRIMARY KEY,
              capture_id TEXT NOT NULL UNIQUE,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              extracted_text TEXT NOT NULL,
              source_language TEXT NOT NULL,
              tags_json TEXT NOT NULL,
              dates_mentioned_json TEXT NOT NULL,
              people_mentioned_json TEXT NOT NULL,
              action_candidates_json TEXT NOT NULL,
              confidence REAL NOT NULL,
              needs_review INTEGER NOT NULL,
              raw_codex_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )

    store.init_db()

    with store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(archive_items)")}
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "core_summary",
        "key_points_json",
        "context",
        "raw_extracted_text",
        "why_saved",
        "primary_interest",
        "secondary_interests_json",
        "topic",
        "subtopic",
        "classification_reason",
        "revisit_priority",
        "revisit_reason",
        "insight_seed",
    } <= columns
    assert {"insight_notes", "insight_note_items"} <= tables


def test_list_capture_summaries_filters_by_primary_or_secondary_interest(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    first_id = store.add_capture(
        capture_key="chat:3",
        chat_id="chat",
        message_id=3,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="AI 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 3},
    )
    second_id = store.add_capture(
        capture_key="chat:4",
        chat_id="chat",
        message_id=4,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="운동 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 4},
    )
    store.upsert_archive_item(
        first_id,
        {
            "title": "AI 글",
            "core_summary": "AI 요약",
            "raw_extracted_text": "AI 글",
            "source_language": "ko",
            "primary_interest": "AI",
            "secondary_interests": ["career"],
            "topic": "agents",
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    store.upsert_archive_item(
        second_id,
        {
            "title": "운동 글",
            "core_summary": "운동 요약",
            "raw_extracted_text": "운동 글",
            "source_language": "ko",
            "primary_interest": "health",
            "secondary_interests": ["lifestyle"],
            "topic": "training",
            "confidence": 0.8,
            "needs_review": False,
        },
    )

    ai_rows = store.list_capture_summaries(10, interest="AI")
    career_rows = store.list_capture_summaries(10, interest="career")

    assert [row["id"] for row in ai_rows] == [first_id]
    assert [row["id"] for row in career_rows] == [first_id]
