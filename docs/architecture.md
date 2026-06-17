# 다카이브봇 아키텍처

다카이브봇은 Telegram을 개인 캡처함으로 쓰고, 로컬 SQLite를 영구 저장소로 쓰는 개인 아카이브 봇입니다.

## 흐름

```text
Telegram message/photo/document
  -> darchive telegram
  -> captures/capture_files SQLite rows
  -> downloaded media under .local/captures/

launchd/cron
  -> darchive process --export-graph
  -> pending capture packet
  -> codex exec with JSON Schema
  -> validated archive_items/extracted_texts SQLite rows
  -> if any capture was processed, rebuild semantic graph from validated archive_items SQLite rows
  -> RDF store under .local/graph/semantic-store/
  -> lightweight JSON-LD export under .local/graph/darchivebot.jsonld

manual graph inspection
  -> darchive graph sync
  -> darchive graph stats
  -> darchive graph export
  -> darchive graph store-export

future Viewpoint Layer
  -> graph/readiness inspection
  -> related captures
  -> recurring themes
  -> periodic insight notes
  -> bounded Codex discussion context from the user's archive
```

## 경계

- `telegram`: Telegram polling, chat allow-list, raw message capture, media download.
- `storage`: SQLite schema and deterministic writes.
- `codex_harness`: non-interactive Codex invocation and JSON Schema setup.
- `processor`: pending capture selection, Codex result validation, fallback extraction, state transitions.
- `ocr`: optional local OCR fallback when Codex is disabled.
- `semantic_graph`: pyoxigraph RDF store sync, stats, and N-Quads export from validated archive rows.
- `graph`: lightweight JSON-LD portable export from validated archive rows.
- `cli`: setup, doctor, polling, processing, listing, and utility commands.

Codex is intentionally not allowed to write SQLite directly. Codex reads a bounded capture packet and attached images, returns structured JSON, then Python validates and writes the database. This keeps database mutation deterministic and makes retry/failure handling explicit.

The ontology-native graph layer is a semantic memory, not the raw ingestion store. SQLite remains the source of truth for Telegram capture state and processing runs. The pyoxigraph store under `.local/graph/semantic-store/` is the primary semantic layer for interests, topics, concepts, claims, questions, and relation candidates. JSON-LD remains a lightweight portable export, not a full semantic-store backup. Raw extracted text is omitted from graph output by default and only included with an explicit CLI flag.

## Product layers

```text
Capture Layer
  -> Telegram intake and local media storage

Archive Layer
  -> SQLite source of truth for captures, files, extracted text, archive items, and processing runs

Semantic Graph Layer
  -> generated meaning layer for interests, topics, concepts, claims, questions, and relation candidates

Viewpoint Layer
  -> related captures, recurring themes, unresolved questions, project seeds, periodic insight notes, and Codex discussion context
```

The Viewpoint Layer is the final product direction. It should help the user discuss new questions with Codex using bounded context from their own saved archive. It should not bypass the lower layers: every viewpoint output needs evidence from archive items and graph facts.

## Local privacy

Secrets, logs, SQLite files, and captured media live under `.env` and `.local/`, which are gitignored. Telegram files are downloaded immediately so the local archive does not depend only on Telegram `file_id` values.
