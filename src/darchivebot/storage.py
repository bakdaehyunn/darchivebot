from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darchivebot.json_utils import dumps


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS captures (
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
);

CREATE TABLE IF NOT EXISTS capture_files (
  id TEXT PRIMARY KEY,
  capture_id TEXT NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
  telegram_file_id TEXT NOT NULL,
  telegram_file_unique_id TEXT,
  file_kind TEXT NOT NULL,
  mime_type TEXT,
  file_name TEXT,
  file_size INTEGER,
  local_path TEXT,
  download_status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(capture_id, telegram_file_id)
);

CREATE TABLE IF NOT EXISTS extracted_texts (
  id TEXT PRIMARY KEY,
  capture_id TEXT NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  text TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(capture_id, source)
);

CREATE TABLE IF NOT EXISTS archive_items (
  id TEXT PRIMARY KEY,
  capture_id TEXT NOT NULL UNIQUE REFERENCES captures(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  core_summary TEXT,
  key_points_json TEXT,
  context TEXT,
  extracted_text TEXT NOT NULL,
  raw_extracted_text TEXT,
  why_saved TEXT,
  source_language TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  primary_interest TEXT,
  secondary_interests_json TEXT,
  topic TEXT,
  subtopic TEXT,
  classification_reason TEXT,
  revisit_priority TEXT,
  revisit_reason TEXT,
  insight_seed TEXT,
  dates_mentioned_json TEXT NOT NULL,
  people_mentioned_json TEXT NOT NULL,
  action_candidates_json TEXT NOT NULL,
  confidence REAL NOT NULL,
  needs_review INTEGER NOT NULL,
  raw_codex_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processing_runs (
  id TEXT PRIMARY KEY,
  capture_id TEXT REFERENCES captures(id) ON DELETE SET NULL,
  processor TEXT NOT NULL,
  status TEXT NOT NULL,
  input_path TEXT,
  output_path TEXT,
  error TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_captures_status_created ON captures(status, created_at);
CREATE INDEX IF NOT EXISTS idx_capture_files_capture_id ON capture_files(capture_id);
CREATE INDEX IF NOT EXISTS idx_processing_runs_capture_id ON processing_runs(capture_id);
"""


@dataclass(frozen=True)
class CaptureRecord:
    id: str
    capture_key: str
    chat_id: str
    message_id: int
    text: str
    caption: str
    content_kind: str
    status: str


class ArchiveStore:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "darchivebot.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            migrate_db(conn)

    def add_capture(
        self,
        *,
        capture_key: str,
        chat_id: str,
        message_id: int,
        chat_type: str,
        chat_title: str,
        sender_user_id: str,
        sender_name: str,
        message_date: int | None,
        text: str,
        caption: str,
        content_kind: str,
        raw_message: dict[str, Any],
    ) -> str:
        self.init_db()
        now = utc_now()
        message_datetime = unix_to_iso(message_date)
        capture_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO captures(
                  id, capture_key, chat_id, message_id, chat_type, chat_title,
                  sender_user_id, sender_name, message_date, message_datetime,
                  text, caption, content_kind, raw_message_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    capture_id,
                    capture_key,
                    chat_id,
                    message_id,
                    chat_type,
                    chat_title,
                    sender_user_id,
                    sender_name,
                    message_date,
                    message_datetime,
                    text,
                    caption,
                    content_kind,
                    dumps(raw_message),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT id FROM captures WHERE capture_key = ?", (capture_key,)).fetchone()
        if row is None:
            raise RuntimeError("failed to insert or load capture")
        return str(row["id"])

    def add_file(
        self,
        *,
        capture_id: str,
        telegram_file_id: str,
        telegram_file_unique_id: str,
        file_kind: str,
        mime_type: str,
        file_name: str,
        file_size: int | None,
        local_path: str,
        download_status: str,
    ) -> str:
        self.init_db()
        file_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO capture_files(
                  id, capture_id, telegram_file_id, telegram_file_unique_id,
                  file_kind, mime_type, file_name, file_size, local_path,
                  download_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    capture_id,
                    telegram_file_id,
                    telegram_file_unique_id,
                    file_kind,
                    mime_type,
                    file_name,
                    file_size,
                    local_path,
                    download_status,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id FROM capture_files
                WHERE capture_id = ? AND telegram_file_id = ?
                """,
                (capture_id, telegram_file_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to insert or load capture file")
        return str(row["id"])

    def pending_captures(self, limit: int) -> list[sqlite3.Row]:
        self.init_db()
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM captures
                    WHERE status IN ('pending', 'failed_retryable')
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
            )

    def files_for_capture(self, capture_id: str) -> list[sqlite3.Row]:
        self.init_db()
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM capture_files WHERE capture_id = ? ORDER BY created_at ASC",
                    (capture_id,),
                )
            )

    def list_captures(self, limit: int) -> list[sqlite3.Row]:
        self.init_db()
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM captures ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            )

    def list_capture_summaries(self, limit: int, interest: str = "") -> list[sqlite3.Row]:
        self.init_db()
        interest = interest.strip().lower()
        where_clause = ""
        params: list[Any] = []
        if interest:
            where_clause = """
                    WHERE ai.id IS NOT NULL
                      AND (
                        LOWER(COALESCE(ai.primary_interest, '')) = ?
                        OR LOWER(COALESCE(ai.secondary_interests_json, '')) LIKE ?
                      )
                    """
            params.extend([interest, f"%{interest}%"])
        params.append(limit)
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"""
                    SELECT
                      c.*,
                      COUNT(cf.id) AS file_count,
                      COALESCE(GROUP_CONCAT(DISTINCT cf.download_status), '') AS file_download_statuses,
                      CASE WHEN ai.id IS NULL THEN 0 ELSE 1 END AS has_archive_item,
                      COALESCE(ai.title, '') AS archive_title,
                      COALESCE(ai.core_summary, ai.summary, '') AS archive_core_summary,
                      COALESCE(ai.why_saved, '') AS archive_why_saved,
                      COALESCE(ai.primary_interest, '') AS archive_primary_interest,
                      COALESCE(ai.secondary_interests_json, '[]') AS archive_secondary_interests_json,
                      COALESCE(ai.topic, '') AS archive_topic,
                      COALESCE(ai.subtopic, '') AS archive_subtopic,
                      COALESCE(ai.needs_review, 0) AS archive_needs_review
                    FROM captures c
                    LEFT JOIN capture_files cf ON cf.capture_id = c.id
                    LEFT JOIN archive_items ai ON ai.capture_id = c.id
                    {where_clause}
                    GROUP BY c.id
                    ORDER BY c.created_at DESC
                    LIMIT ?
                    """,
                    tuple(params),
                )
            )

    def get_capture(self, capture_id: str) -> sqlite3.Row | None:
        self.init_db()
        with self.connect() as conn:
            return conn.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()

    def get_archive_item(self, capture_id: str) -> sqlite3.Row | None:
        self.init_db()
        with self.connect() as conn:
            return conn.execute("SELECT * FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()

    def mark_capture_status(self, capture_id: str, status: str) -> None:
        self.init_db()
        with self.connect() as conn:
            conn.execute(
                "UPDATE captures SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), capture_id),
            )

    def upsert_extracted_text(
        self,
        *,
        capture_id: str,
        source: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.init_db()
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO extracted_texts(id, capture_id, source, text, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(capture_id, source) DO UPDATE SET
                  text = excluded.text,
                  metadata_json = excluded.metadata_json,
                  updated_at = excluded.updated_at
                """,
                (str(uuid.uuid4()), capture_id, source, text, dumps(metadata or {}), now, now),
            )

    def upsert_archive_item(self, capture_id: str, item: dict[str, Any]) -> None:
        self.init_db()
        now = utc_now()
        title = str(item.get("title") or "").strip() or "Untitled capture"
        core_summary = str(item.get("core_summary") or item.get("summary") or "").strip()
        summary = core_summary
        key_points = list_value(item.get("key_points"))
        context = str(item.get("context") or "").strip()
        raw_extracted_text = str(item.get("raw_extracted_text") or item.get("extracted_text") or "").strip()
        extracted_text = raw_extracted_text
        why_saved = str(item.get("why_saved") or "").strip()
        source_language = str(item.get("source_language") or "unknown").strip() or "unknown"
        primary_interest = str(item.get("primary_interest") or "other/unknown").strip() or "other/unknown"
        secondary_interests = list_value(item.get("secondary_interests"))
        topic = str(item.get("topic") or "").strip()
        subtopic = str(item.get("subtopic") or "").strip()
        classification_reason = str(item.get("classification_reason") or "").strip()
        revisit_priority = str(item.get("revisit_priority") or "medium").strip().lower() or "medium"
        revisit_reason = str(item.get("revisit_reason") or "").strip()
        insight_seed = str(item.get("insight_seed") or "").strip()
        confidence = float(item.get("confidence") or 0.0)
        needs_review = 1 if bool(item.get("needs_review")) else 0
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO archive_items(
                  id, capture_id, title, summary, core_summary, key_points_json,
                  context, extracted_text, raw_extracted_text, why_saved, source_language,
                  tags_json, primary_interest, secondary_interests_json, topic, subtopic,
                  classification_reason, revisit_priority, revisit_reason, insight_seed,
                  dates_mentioned_json, people_mentioned_json,
                  action_candidates_json, confidence, needs_review, raw_codex_json,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(capture_id) DO UPDATE SET
                  title = excluded.title,
                  summary = excluded.summary,
                  core_summary = excluded.core_summary,
                  key_points_json = excluded.key_points_json,
                  context = excluded.context,
                  extracted_text = excluded.extracted_text,
                  raw_extracted_text = excluded.raw_extracted_text,
                  why_saved = excluded.why_saved,
                  source_language = excluded.source_language,
                  tags_json = excluded.tags_json,
                  primary_interest = excluded.primary_interest,
                  secondary_interests_json = excluded.secondary_interests_json,
                  topic = excluded.topic,
                  subtopic = excluded.subtopic,
                  classification_reason = excluded.classification_reason,
                  revisit_priority = excluded.revisit_priority,
                  revisit_reason = excluded.revisit_reason,
                  insight_seed = excluded.insight_seed,
                  dates_mentioned_json = excluded.dates_mentioned_json,
                  people_mentioned_json = excluded.people_mentioned_json,
                  action_candidates_json = excluded.action_candidates_json,
                  confidence = excluded.confidence,
                  needs_review = excluded.needs_review,
                  raw_codex_json = excluded.raw_codex_json,
                  updated_at = excluded.updated_at
                """,
                (
                    str(uuid.uuid4()),
                    capture_id,
                    title,
                    summary,
                    core_summary,
                    dumps(key_points),
                    context,
                    extracted_text,
                    raw_extracted_text,
                    why_saved,
                    source_language,
                    dumps(list_value(item.get("tags"))),
                    primary_interest,
                    dumps(secondary_interests),
                    topic,
                    subtopic,
                    classification_reason,
                    revisit_priority,
                    revisit_reason,
                    insight_seed,
                    dumps(list_value(item.get("dates_mentioned"))),
                    dumps(list_value(item.get("people_mentioned"))),
                    dumps(list_value(item.get("action_candidates"))),
                    confidence,
                    needs_review,
                    dumps(item),
                    now,
                    now,
                ),
            )

    def start_processing_run(
        self,
        *,
        capture_id: str,
        processor: str,
        input_path: str = "",
    ) -> str:
        self.init_db()
        run_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO processing_runs(id, capture_id, processor, status, input_path, started_at)
                VALUES (?, ?, ?, 'running', ?, ?)
                """,
                (run_id, capture_id, processor, input_path, utc_now()),
            )
        return run_id

    def finish_processing_run(
        self,
        *,
        run_id: str,
        status: str,
        output_path: str = "",
        error: str = "",
    ) -> None:
        self.init_db()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE processing_runs
                SET status = ?, output_path = ?, error = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, output_path, error, utc_now(), run_id),
            )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unix_to_iso(value: int | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(timespec="seconds")


def list_value(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def migrate_db(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(archive_items)")}
    additions = {
        "core_summary": "TEXT",
        "key_points_json": "TEXT",
        "context": "TEXT",
        "raw_extracted_text": "TEXT",
        "why_saved": "TEXT",
        "primary_interest": "TEXT",
        "secondary_interests_json": "TEXT",
        "topic": "TEXT",
        "subtopic": "TEXT",
        "classification_reason": "TEXT",
        "revisit_priority": "TEXT",
        "revisit_reason": "TEXT",
        "insight_seed": "TEXT",
    }
    for column, column_type in additions.items():
        if column not in columns:
            try:
                conn.execute(f"ALTER TABLE archive_items ADD COLUMN {column} {column_type}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
