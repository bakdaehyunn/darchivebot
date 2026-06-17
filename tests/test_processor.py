from __future__ import annotations

from pathlib import Path
from typing import Any

from darchivebot.processor import CaptureProcessor
from darchivebot.storage import ArchiveStore

from conftest import make_settings


class FakeCodex:
    def __init__(self) -> None:
        self.seen_packets: list[dict[str, Any]] = []
        self.seen_images: list[list[Path]] = []

    def process_capture(self, packet: dict[str, Any], image_paths: list[Path]) -> dict[str, Any]:
        self.seen_packets.append(packet)
        self.seen_images.append(image_paths)
        return {
            "capture_id": packet["capture_id"],
            "content_type": packet["content_kind"],
            "title": "정리된 제목",
            "core_summary": "이미지 안의 핵심 내용",
            "key_points": ["첫 번째 핵심", "두 번째 핵심"],
            "context": "screenshot",
            "raw_extracted_text": packet.get("text") or packet.get("caption") or "image text",
            "why_saved": "나중에 다시 볼 만한 참고 내용",
            "source_language": "ko",
            "tags": ["archive", "screenshot"],
            "primary_interest": "AI",
            "secondary_interests": ["career"],
            "topic": "agent archive",
            "subtopic": "personal knowledge workflow",
            "classification_reason": "AI workflow capture about archiving",
            "revisit_priority": "high",
            "revisit_reason": "can shape the archive product direction",
            "insight_seed": "connects AI agents with personal archives",
            "dates_mentioned": [],
            "people_mentioned": [],
            "action_candidates": [],
            "confidence": 0.8,
            "needs_review": False,
        }


class EmptyOcr:
    def extract_text(self, path: Path) -> str:
        return ""


class ExplodingCodex:
    def process_capture(self, packet: dict[str, Any], image_paths: list[Path]) -> dict[str, Any]:
        raise AssertionError("codex should not be called")


def add_text_capture(store: ArchiveStore, message_id: int = 1) -> str:
    return store.add_capture(
        capture_key=f"chat:{message_id}",
        chat_id="chat",
        message_id=message_id,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="관심 글 본문",
        caption="",
        content_kind="text",
        raw_message={"message_id": message_id},
    )


def test_processor_uses_codex_and_writes_archive_item(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_text_capture(store)
    fake_codex = FakeCodex()

    results = CaptureProcessor(settings, store, codex=fake_codex, ocr=EmptyOcr()).process_pending()

    assert results[0]["capture_id"] == capture_id
    assert results[0]["status"] == "processed"
    assert results[0]["processor"] == "codex"
    assert fake_codex.seen_packets[0]["text"] == "관심 글 본문"
    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "processed"
    with store.connect() as conn:
        archive = conn.execute("SELECT * FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()
    assert archive["title"] == "정리된 제목"
    assert archive["core_summary"] == "이미지 안의 핵심 내용"
    assert archive["summary"] == "이미지 안의 핵심 내용"
    assert archive["raw_extracted_text"] == "관심 글 본문"
    assert archive["primary_interest"] == "AI"
    assert archive["topic"] == "agent archive"
    assert archive["revisit_priority"] == "high"


def test_processor_basic_fallback_when_codex_disabled(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=False)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_text_capture(store)

    results = CaptureProcessor(settings, store, codex=FakeCodex(), ocr=EmptyOcr()).process_pending()

    assert results[0]["capture_id"] == capture_id
    assert results[0]["status"] == "processed"
    assert results[0]["processor"] == "basic"
    with store.connect() as conn:
        archive = conn.execute("SELECT * FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()
    assert archive["extracted_text"] == "관심 글 본문"
    assert archive["raw_extracted_text"] == "관심 글 본문"
    assert archive["core_summary"] == "관심 글 본문"
    assert archive["primary_interest"] == "other/unknown"
    assert archive["needs_review"] == 1


def test_processor_sends_photo_image_to_codex_and_stores_structured_fields(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)
    image_path = settings.media_dir / "capture.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake image bytes")
    capture_id = store.add_capture(
        capture_key="chat:20",
        chat_id="chat",
        message_id=20,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="",
        caption="",
        content_kind="photo",
        raw_message={"message_id": 20},
    )
    store.add_file(
        capture_id=capture_id,
        telegram_file_id="file-id",
        telegram_file_unique_id="unique",
        file_kind="photo",
        mime_type="image/jpeg",
        file_name="capture.jpg",
        file_size=123,
        local_path=str(image_path),
        download_status="downloaded",
    )
    fake_codex = FakeCodex()

    results = CaptureProcessor(settings, store, codex=fake_codex, ocr=EmptyOcr()).process_pending()

    assert results[0]["status"] == "processed"
    assert fake_codex.seen_images == [[image_path]]
    with store.connect() as conn:
        archive = conn.execute("SELECT * FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()
    assert archive["context"] == "screenshot"
    assert "첫 번째 핵심" in archive["key_points_json"]
    assert archive["why_saved"] == "나중에 다시 볼 만한 참고 내용"
    assert archive["classification_reason"] == "AI workflow capture about archiving"
    assert archive["insight_seed"] == "connects AI agents with personal archives"


def test_processor_with_no_pending_exits_without_codex(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)

    results = CaptureProcessor(settings, store, codex=ExplodingCodex(), ocr=EmptyOcr()).process_pending()

    assert results == []


def test_processor_records_failed_codex_run_as_retryable(tmp_path):
    class FailingCodex:
        def process_capture(self, packet: dict[str, Any], image_paths: list[Path]) -> dict[str, Any]:
            raise RuntimeError("codex failed")

    settings = make_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_text_capture(store)

    results = CaptureProcessor(settings, store, codex=FailingCodex(), ocr=EmptyOcr()).process_pending()

    assert results[0]["status"] == "failed"
    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "failed_retryable"


def test_reprocess_capture_rewrites_archive_item(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_text_capture(store)
    store.upsert_archive_item(
        capture_id,
        {
            "title": "Old title",
            "core_summary": "Old summary",
            "raw_extracted_text": "Old text",
            "source_language": "ko",
            "primary_interest": "other/unknown",
            "topic": "",
            "confidence": 0.2,
            "needs_review": True,
        },
    )
    store.mark_capture_status(capture_id, "processed")
    fake_codex = FakeCodex()

    result = CaptureProcessor(settings, store, codex=fake_codex, ocr=EmptyOcr()).reprocess_capture(capture_id)

    assert result["status"] == "processed"
    assert fake_codex.seen_packets[0]["capture_id"] == capture_id
    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "processed"
    archive = store.get_archive_item(capture_id)
    assert archive is not None
    assert archive["title"] == "정리된 제목"
    assert archive["primary_interest"] == "AI"
    assert archive["needs_review"] == 0


def test_reprocess_capture_failure_preserves_existing_status_and_archive_item(tmp_path):
    class FailingCodex:
        def process_capture(self, packet: dict[str, Any], image_paths: list[Path]) -> dict[str, Any]:
            raise RuntimeError("codex failed during reprocess")

    settings = make_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_text_capture(store)
    store.upsert_archive_item(
        capture_id,
        {
            "title": "Keep this",
            "core_summary": "Do not overwrite",
            "raw_extracted_text": "Original extracted text",
            "source_language": "ko",
            "primary_interest": "career",
            "topic": "writing",
            "confidence": 0.7,
            "needs_review": False,
        },
    )
    store.mark_capture_status(capture_id, "processed")

    result = CaptureProcessor(settings, store, codex=FailingCodex(), ocr=EmptyOcr()).reprocess_capture(capture_id)

    assert result["status"] == "failed"
    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "processed"
    archive = store.get_archive_item(capture_id)
    assert archive is not None
    assert archive["title"] == "Keep this"
    assert archive["primary_interest"] == "career"
    with store.connect() as conn:
        run = conn.execute(
            "SELECT * FROM processing_runs WHERE capture_id = ? ORDER BY started_at DESC LIMIT 1",
            (capture_id,),
        ).fetchone()
    assert run["status"] == "failed"
    assert "codex failed during reprocess" in run["error"]


def test_processor_skips_empty_capture_without_archive_item(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)
    capture_id = store.add_capture(
        capture_key="chat:99",
        chat_id="chat",
        message_id=99,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="",
        caption="",
        content_kind="text",
        raw_message={"message_id": 99},
    )

    results = CaptureProcessor(settings, store, codex=FakeCodex(), ocr=EmptyOcr()).process_pending()

    assert results[0]["status"] == "skipped_empty"
    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "skipped_empty"
    with store.connect() as conn:
        archive_count = conn.execute("SELECT COUNT(*) FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()[0]
    assert archive_count == 0


def test_processor_emits_progress_events(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=False)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_text_capture(store)
    events: list[dict[str, Any]] = []

    results = CaptureProcessor(settings, store, codex=FakeCodex(), ocr=EmptyOcr()).process_pending(progress=events.append)

    assert results[0]["status"] == "processed"
    assert [event["event"] for event in events] == ["start", "finish"]
    assert events[0]["capture_id"] == capture_id
    assert events[1]["elapsed_sec"] >= 0
