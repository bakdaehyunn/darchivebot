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
            "questions": ["어떻게 꾸준히 읽을까?"],
            "relation_candidates": ["reading system"],
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
    assert "어떻게 꾸준히 읽을까?" in archive["questions_json"]
    assert "reading system" in archive["relation_candidates_json"]
    interpretations = store.archive_interpretations_for_capture(capture_id)
    assert len(interpretations) == 1
    assert interpretations[0]["title"] == "읽을 글"
    assert interpretations[0]["source"] == "unknown"


def test_search_index_rebuild_is_deterministic_and_searchable(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:search",
        chat_id="chat",
        message_id=22,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="semantic archive capture",
        caption="",
        content_kind="text",
        raw_message={"message_id": 22},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "Semantic archive design",
            "core_summary": "FTS search should find reusable archive notes",
            "key_points": ["local retrieval matters"],
            "raw_extracted_text": "A local-first archive needs full text retrieval.",
            "source_language": "en",
            "tags": ["search", "archive"],
            "primary_interest": "AI",
            "secondary_interests": ["product"],
            "topic": "retrieval",
            "questions": ["How do I find this later?"],
            "insight_seed": "Search layer before viewpoint layer",
            "confidence": 0.9,
            "needs_review": False,
        },
    )

    first = store.rebuild_search_index()
    second = store.rebuild_search_index()
    rows = store.search_archive('"retrieval"', limit=10)

    assert first == second == {"indexed_archive_items": 1}
    assert len(rows) == 1
    assert rows[0]["capture_id"] == capture_id
    assert "retrieval" in rows[0]["search_topics"]


def test_search_index_refreshes_when_extracted_text_changes_after_archive_item(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:search-refresh",
        chat_id="chat",
        message_id=25,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="initial",
        caption="",
        content_kind="text",
        raw_message={"message_id": 25},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "Archive item",
            "core_summary": "Search refresh",
            "raw_extracted_text": "initial text",
            "source_language": "en",
            "primary_interest": "AI",
            "topic": "search",
            "confidence": 0.9,
            "needs_review": False,
        },
    )

    assert store.search_archive('"latekeyword"', limit=10) == []

    store.upsert_extracted_text(capture_id=capture_id, source="ocr", text="latekeyword from updated OCR")

    rows = store.search_archive('"latekeyword"', limit=10)
    assert len(rows) == 1
    assert rows[0]["capture_id"] == capture_id
    assert "latekeyword" in rows[0]["search_source_text"]


def test_review_archive_items_filters_needs_review_and_revisit(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    review_id = store.add_capture(
        capture_key="chat:review",
        chat_id="chat",
        message_id=23,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="needs review",
        caption="",
        content_kind="text",
        raw_message={"message_id": 23},
    )
    revisit_id = store.add_capture(
        capture_key="chat:revisit",
        chat_id="chat",
        message_id=24,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="revisit",
        caption="",
        content_kind="text",
        raw_message={"message_id": 24},
    )
    store.upsert_archive_item(
        review_id,
        {
            "title": "Weak capture",
            "core_summary": "Needs human review",
            "raw_extracted_text": "Needs human review",
            "source_language": "en",
            "primary_interest": "other/unknown",
            "topic": "",
            "confidence": 0.2,
            "needs_review": True,
        },
    )
    store.upsert_archive_item(
        revisit_id,
        {
            "title": "Useful project seed",
            "core_summary": "Return to this later",
            "raw_extracted_text": "Return to this later",
            "source_language": "en",
            "primary_interest": "product",
            "topic": "archive",
            "revisit_priority": "high",
            "revisit_reason": "convert into product task",
            "insight_seed": "local search workflow",
            "confidence": 0.8,
            "needs_review": False,
        },
    )

    needs_review = store.review_archive_items(needs_review_only=True)
    revisit = store.review_archive_items(revisit_only=True)

    assert [row["capture_id"] for row in needs_review] == [review_id]
    assert [row["capture_id"] for row in revisit] == [revisit_id]


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
        "questions_json",
        "relation_candidates_json",
    } <= columns
    assert {"archive_interpretations", "insight_notes", "insight_note_items"} <= tables


def test_init_db_adds_retry_columns_to_existing_captures_table_before_index(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            """
            CREATE TABLE captures (
              id TEXT PRIMARY KEY,
              capture_key TEXT NOT NULL UNIQUE,
              chat_id TEXT NOT NULL,
              message_id INTEGER NOT NULL,
              chat_type TEXT,
              chat_title TEXT,
              sender_user_id TEXT,
              sender_name TEXT,
              message_date INTEGER,
              message_datetime TEXT,
              text TEXT,
              caption TEXT,
              content_kind TEXT NOT NULL,
              raw_message_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )

    store.init_db()

    with store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(captures)")}
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(captures)")}
    assert {"retry_count", "next_retry_at", "last_error"} <= columns
    assert "idx_captures_retry" in indexes


def test_pending_captures_respect_retry_backoff_and_blocked_status(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:retry",
        chat_id="chat",
        message_id=100,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="retry me",
        caption="",
        content_kind="text",
        raw_message={"message_id": 100},
    )

    first_failure = store.mark_capture_failed(capture_id, error="temporary codex failure", max_attempts=3)

    assert first_failure["status"] == "failed_retryable"
    assert first_failure["retry_count"] == 1
    assert first_failure["next_retry_at"]
    assert store.pending_captures(10) == []

    with store.connect() as conn:
        conn.execute("UPDATE captures SET next_retry_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (capture_id,))
    assert [row["id"] for row in store.pending_captures(10)] == [capture_id]

    store.mark_capture_failed(capture_id, error="temporary codex failure", max_attempts=3)
    blocked = store.mark_capture_failed(capture_id, error="still failing", max_attempts=3)

    row = store.get_capture(capture_id)
    assert row is not None
    assert blocked["status"] == "failed_blocked"
    assert row["status"] == "failed_blocked"
    assert row["retry_count"] == 3
    assert row["last_error"] == "still failing"
    assert store.pending_captures(10) == []


def test_mark_capture_processed_resets_retry_state(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:retry-reset",
        chat_id="chat",
        message_id=101,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="retry reset",
        caption="",
        content_kind="text",
        raw_message={"message_id": 101},
    )
    store.mark_capture_failed(capture_id, error="temporary codex failure")

    store.mark_capture_processed(capture_id)

    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "processed"
    assert row["retry_count"] == 0
    assert row["next_retry_at"] == ""
    assert row["last_error"] == ""


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
