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
            "summary": "정리된 요약",
            "extracted_text": packet.get("text") or packet.get("caption") or "image text",
            "source_language": "ko",
            "tags": ["archive"],
            "dates_mentioned": [],
            "people_mentioned": [],
            "action_candidates": [],
            "confidence": 0.8,
            "needs_review": False,
        }


class EmptyOcr:
    def extract_text(self, path: Path) -> str:
        return ""


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

    assert results == [{"capture_id": capture_id, "status": "processed"}]
    assert fake_codex.seen_packets[0]["text"] == "관심 글 본문"
    row = store.get_capture(capture_id)
    assert row is not None
    assert row["status"] == "processed"
    with store.connect() as conn:
        archive = conn.execute("SELECT * FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()
    assert archive["title"] == "정리된 제목"


def test_processor_basic_fallback_when_codex_disabled(tmp_path):
    settings = make_settings(tmp_path, codex_enabled=False)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_text_capture(store)

    results = CaptureProcessor(settings, store, codex=FakeCodex(), ocr=EmptyOcr()).process_pending()

    assert results == [{"capture_id": capture_id, "status": "processed"}]
    with store.connect() as conn:
        archive = conn.execute("SELECT * FROM archive_items WHERE capture_id = ?", (capture_id,)).fetchone()
    assert archive["extracted_text"] == "관심 글 본문"
    assert archive["needs_review"] == 1


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
