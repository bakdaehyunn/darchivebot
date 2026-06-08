# 다카이브봇 아키텍처

다카이브봇은 Telegram을 개인 캡처함으로 쓰고, 로컬 SQLite를 영구 저장소로 쓰는 개인 아카이브 봇입니다.

## 흐름

```text
Telegram message/photo/document
  -> darchive telegram
  -> captures/capture_files SQLite rows
  -> downloaded media under .local/captures/

launchd/cron
  -> darchive process
  -> pending capture packet
  -> codex exec with JSON Schema
  -> validated archive_items/extracted_texts SQLite rows

local graph export
  -> darchive graph export
  -> validated archive_items SQLite rows
  -> JSON-LD graph under .local/graph/darchivebot.jsonld
```

## 경계

- `telegram`: Telegram polling, chat allow-list, raw message capture, media download.
- `storage`: SQLite schema and deterministic writes.
- `codex_harness`: non-interactive Codex invocation and JSON Schema setup.
- `processor`: pending capture selection, Codex result validation, fallback extraction, state transitions.
- `ocr`: optional local OCR fallback when Codex is disabled.
- `graph`: JSON-LD graph export from validated archive rows.
- `cli`: setup, doctor, polling, processing, listing, and utility commands.

Codex is intentionally not allowed to write SQLite directly. Codex reads a bounded capture packet and attached images, returns structured JSON, then Python validates and writes the database. This keeps database mutation deterministic and makes retry/failure handling explicit.

The ontology-native graph layer is a semantic read model, not the raw ingestion store. SQLite remains the source of truth for Telegram capture state and processing runs; graph files are regenerated from validated archive rows.

## Local privacy

Secrets, logs, SQLite files, and captured media live under `.env` and `.local/`, which are gitignored. Telegram files are downloaded immediately so the local archive does not depend only on Telegram `file_id` values.
