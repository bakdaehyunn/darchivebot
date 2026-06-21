from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from darchivebot.codex_harness import (
    CAPTURE_PROMPT_VERSION,
    CAPTURE_SCHEMA_VERSION,
    CodexHarness,
    CodexRunError,
    validate_codex_item,
)
from darchivebot.config import Settings
from darchivebot.ocr import OcrAdapter, TesseractOcrAdapter
from darchivebot.state import file_lock
from darchivebot.storage import ArchiveStore


class CaptureProcessor:
    def __init__(
        self,
        settings: Settings,
        store: ArchiveStore,
        codex: CodexHarness | None = None,
        ocr: OcrAdapter | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.codex = codex or CodexHarness(settings)
        self.ocr = ocr or TesseractOcrAdapter(settings.tesseract_bin)

    def process_pending(
        self,
        *,
        limit: int | None = None,
        dry_run: bool = False,
        use_codex: bool | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        actual_limit = limit or self.settings.processor_batch_size
        lock_path = self.settings.state_dir / "locks" / "processor.lock"
        with file_lock(lock_path) as acquired:
            if not acquired:
                return [{"status": "skipped", "reason": "processor lock is already held"}]
            return self._process_pending_unlocked(
                limit=actual_limit,
                dry_run=dry_run,
                use_codex=use_codex,
                progress=progress,
            )

    def _process_pending_unlocked(
        self,
        *,
        limit: int,
        dry_run: bool,
        use_codex: bool | None,
        progress: Callable[[dict[str, Any]], None] | None,
    ) -> list[dict[str, Any]]:
        captures = self.store.pending_captures(limit)
        results: list[dict[str, Any]] = []
        codex_enabled = self.settings.codex_enabled if use_codex is None else use_codex
        for capture in captures:
            results.append(
                self._process_capture_row(
                    capture,
                    dry_run=dry_run,
                    codex_enabled=codex_enabled,
                    progress=progress,
                    preserve_status_on_failure=False,
                )
            )
        return results

    def reprocess_capture(
        self,
        capture_id: str,
        *,
        use_codex: bool | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        lock_path = self.settings.state_dir / "locks" / "processor.lock"
        with file_lock(lock_path) as acquired:
            if not acquired:
                return {"capture_id": capture_id, "status": "skipped", "reason": "processor lock is already held"}
            capture = self.store.get_capture(capture_id)
            if capture is None:
                return {"capture_id": capture_id, "status": "not_found", "reason": "capture does not exist"}
            codex_enabled = self.settings.codex_enabled if use_codex is None else use_codex
            return self._process_capture_row(
                capture,
                dry_run=False,
                codex_enabled=codex_enabled,
                progress=progress,
                preserve_status_on_failure=True,
            )

    def _process_capture_row(
        self,
        capture: Any,
        *,
        dry_run: bool,
        codex_enabled: bool,
        progress: Callable[[dict[str, Any]], None] | None,
        preserve_status_on_failure: bool,
    ) -> dict[str, Any]:
        capture_id = str(capture["id"])
        files = self.store.files_for_capture(capture_id)
        packet = build_capture_packet(capture, files)
        image_paths = image_paths_for_files(files)
        processor_name = "codex" if codex_enabled else "basic"
        if not has_processable_content(packet, files):
            result = {
                "capture_id": capture_id,
                "status": "skipped_empty",
                "processor": processor_name,
                "content_kind": packet["content_kind"],
                "file_count": len(files),
                "reason": "no text, caption, or downloaded files",
            }
            if not dry_run and not preserve_status_on_failure:
                self.store.mark_capture_status(capture_id, "skipped_empty")
            if progress:
                progress({"event": "skipped", **result})
            return result
        if dry_run:
            return {
                "capture_id": capture_id,
                "status": "dry-run",
                "processor": processor_name,
                "content_kind": packet["content_kind"],
                "file_count": len(files),
                "image_paths": [str(path) for path in image_paths],
                "text_preview": preview_text(packet),
                "packet": packet,
            }
        started = time.monotonic()
        if progress:
            progress(
                {
                    "event": "start",
                    "capture_id": capture_id,
                    "processor": processor_name,
                    "content_kind": packet["content_kind"],
                    "file_count": len(files),
                }
            )
        run_id = self.store.start_processing_run(
            capture_id=capture_id,
            processor=processor_name,
        )
        try:
            if codex_enabled:
                item = self.codex.process_capture(packet, image_paths)
                item = validate_codex_item(item, capture_id)
            else:
                item = self.basic_extract(packet, files)
            source = "codex" if codex_enabled else "basic"
            self.write_item(
                capture_id,
                item,
                source=source,
                schema_version=CAPTURE_SCHEMA_VERSION if codex_enabled else "basic-fallback-v1",
                prompt_version=CAPTURE_PROMPT_VERSION if codex_enabled else "basic-fallback-v1",
            )
            self.store.mark_capture_processed(capture_id)
            self.store.finish_processing_run(run_id=run_id, status="processed")
            elapsed_sec = time.monotonic() - started
            result = {
                "capture_id": capture_id,
                "status": "processed",
                "processor": processor_name,
                "content_kind": packet["content_kind"],
                "elapsed_sec": round(elapsed_sec, 2),
            }
            if progress:
                progress({"event": "finish", **result})
            return result
        except (CodexRunError, ValueError, OSError, RuntimeError) as exc:
            retry_state = None
            if not preserve_status_on_failure:
                retry_state = self.store.mark_capture_failed(capture_id, error=str(exc))
            self.store.finish_processing_run(run_id=run_id, status="failed", error=str(exc)[:4000])
            elapsed_sec = time.monotonic() - started
            result = {
                "capture_id": capture_id,
                "status": "failed",
                "processor": processor_name,
                "content_kind": packet["content_kind"],
                "elapsed_sec": round(elapsed_sec, 2),
                "error": str(exc),
            }
            if retry_state is not None:
                result.update(
                    {
                        "capture_status": retry_state["status"],
                        "retry_count": retry_state["retry_count"],
                        "next_retry_at": retry_state["next_retry_at"],
                    }
                )
            if progress:
                progress({"event": "failed", **result})
            return result

    def basic_extract(self, packet: dict[str, Any], files: list[Any]) -> dict[str, Any]:
        text_parts = [
            str(packet.get("text") or "").strip(),
            str(packet.get("caption") or "").strip(),
        ]
        for row in files:
            local_path = str(row["local_path"] or "")
            if local_path and is_image_path(Path(local_path)):
                extracted = self.ocr.extract_text(Path(local_path)).strip()
                if extracted:
                    text_parts.append(extracted)
        extracted_text = "\n\n".join(part for part in text_parts if part)
        title = first_title(extracted_text) or f"Capture {packet.get('message_id')}"
        return {
            "capture_id": str(packet["capture_id"]),
            "content_type": str(packet.get("content_kind") or "unknown"),
            "title": title,
            "core_summary": extracted_text[:300],
            "key_points": [],
            "context": "local fallback extraction",
            "raw_extracted_text": extracted_text,
            "why_saved": "",
            "source_language": "unknown",
            "tags": [],
            "primary_interest": "other/unknown",
            "secondary_interests": [],
            "topic": "",
            "subtopic": "",
            "classification_reason": "local fallback did not classify the capture semantically",
            "revisit_priority": "medium",
            "revisit_reason": "",
            "insight_seed": "",
            "questions": [],
            "relation_candidates": [],
            "dates_mentioned": [],
            "people_mentioned": [],
            "action_candidates": [],
            "confidence": 0.25 if extracted_text else 0.0,
            "needs_review": True,
        }

    def write_item(
        self,
        capture_id: str,
        item: dict[str, Any],
        *,
        source: str,
        schema_version: str,
        prompt_version: str,
    ) -> None:
        text = str(item.get("raw_extracted_text") or item.get("extracted_text") or "")
        if text:
            self.store.upsert_extracted_text(capture_id=capture_id, source=source, text=text, metadata=item)
        self.store.upsert_archive_item(
            capture_id,
            item,
            source=source,
            schema_version=schema_version,
            prompt_version=prompt_version,
        )


def build_capture_packet(capture: Any, files: list[Any]) -> dict[str, Any]:
    return {
        "capture_id": str(capture["id"]),
        "capture_key": str(capture["capture_key"]),
        "chat_id": str(capture["chat_id"]),
        "message_id": int(capture["message_id"]),
        "message_datetime": str(capture["message_datetime"] or ""),
        "content_kind": str(capture["content_kind"] or ""),
        "text": str(capture["text"] or ""),
        "caption": str(capture["caption"] or ""),
        "files": [
            {
                "id": str(row["id"]),
                "file_kind": str(row["file_kind"] or ""),
                "mime_type": str(row["mime_type"] or ""),
                "file_name": str(row["file_name"] or ""),
                "local_path": str(row["local_path"] or ""),
                "download_status": str(row["download_status"] or ""),
            }
            for row in files
        ],
    }


def image_paths_for_files(files: list[Any]) -> list[Path]:
    paths: list[Path] = []
    for row in files:
        local_path = str(row["local_path"] or "")
        if local_path and is_image_path(Path(local_path)) and Path(local_path).exists():
            paths.append(Path(local_path))
    return paths


def has_processable_content(packet: dict[str, Any], files: list[Any]) -> bool:
    if str(packet.get("text") or "").strip() or str(packet.get("caption") or "").strip():
        return True
    return any(str(row["download_status"] or "") == "downloaded" and str(row["local_path"] or "") for row in files)


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp"}


def first_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:80]
    return ""


def preview_text(packet: dict[str, Any]) -> str:
    text = str(packet.get("text") or packet.get("caption") or "").replace("\n", " ").strip()
    return text[:120]


def format_results(results: list[dict[str, Any]], json_output: bool) -> str:
    if json_output:
        return json.dumps(results, ensure_ascii=False, indent=2)
    lines = []
    for item in results:
        line = f"{item.get('capture_id', '-')}: {item.get('status', '-')}"
        if item.get("processor"):
            line += f" processor={item['processor']}"
        if item.get("content_kind"):
            line += f" kind={item['content_kind']}"
        if item.get("file_count") is not None:
            line += f" files={item['file_count']}"
        if item.get("image_paths"):
            line += f" images={len(item['image_paths'])}"
        if item.get("reason"):
            line += f" ({item['reason']})"
        if item.get("error"):
            line += f" - {item['error']}"
        if item.get("elapsed_sec") is not None:
            line += f" elapsed={item['elapsed_sec']}s"
        if item.get("text_preview"):
            line += f" :: {item['text_preview']}"
        lines.append(line)
    return "\n".join(lines) if lines else "nothing to process"
