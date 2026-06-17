# Insight synthesis design

This document defines one implementation track inside 다카이브봇's Viewpoint Layer. It is a design only; it does not authorize migrations or implementation by itself.

## Product purpose

The archive layer answers: "What did I save, and what is it about?"

The Viewpoint Layer should eventually answer:

- What am I repeatedly saving?
- Which captures are related?
- What themes are becoming visible over time?
- Which saved ideas are worth revisiting now?
- Is there a project, decision, question, or habit forming across multiple captures?

The layer must not collapse all captures into one generic summary. Each archive item remains individually useful. Insight synthesis sits inside the Viewpoint Layer and connects those items when there is enough evidence.

Layer position:

```text
Capture Layer
  -> Archive Layer
  -> Semantic Graph Layer
  -> Viewpoint Layer
       -> related captures
       -> recurring themes
       -> periodic insight notes
       -> Codex discussion context
```

The Viewpoint Layer is broader than insight notes. It is the layer that turns saved material into personal viewpoint context for future Codex discussion.

## Current foundation

The current archive item already stores enough signal to start synthesis:

- `primary_interest`
- `secondary_interests`
- `topic`
- `subtopic`
- `classification_reason`
- `revisit_priority`
- `revisit_reason`
- `insight_seed`
- `title`
- `core_summary`
- `key_points`
- `raw_extracted_text`
- `why_saved`
- `tags`
- `confidence`
- `needs_review`

Python owns selection, validation, and SQLite writes. Codex reads selected packets and returns structured JSON only.

## Data concepts

### Related captures

Related captures are edges between existing archive items.

Purpose:
- show "this connects to that"
- make one saved item lead to older relevant items
- provide input for theme and insight generation

Proposed fields:
- `id`
- `source_archive_item_id`
- `target_archive_item_id`
- `relation_type`
- `reason`
- `shared_interests_json`
- `shared_topics_json`
- `confidence`
- `needs_review`
- `created_at`
- `updated_at`

Suggested `relation_type` values:
- `same_topic`
- `same_interest`
- `supports`
- `contrasts`
- `updates`
- `example_of`
- `possible_project`
- `unknown`

### Recurring themes

Recurring themes are clusters or patterns found across multiple archive items.

Purpose:
- identify repeated interests
- make saved fragments feel like a developing body of thought
- provide the basis for periodic notes

Proposed fields:
- `id`
- `title`
- `summary`
- `primary_interest`
- `secondary_interests_json`
- `topics_json`
- `archive_item_ids_json`
- `evidence_count`
- `theme_status`
- `confidence`
- `needs_review`
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

Suggested `theme_status` values:
- `emerging`
- `active`
- `stable`
- `stale`
- `dismissed`

### Periodic insight notes

Periodic insight notes are generated summaries over a time window.

Purpose:
- show what mattered this week or month
- connect repeated captures into a readable note
- identify unresolved questions and useful next reviews

Proposed fields:
- `id`
- `period_type`
- `period_start`
- `period_end`
- `title`
- `summary`
- `recurring_themes_json`
- `related_capture_groups_json`
- `notable_archive_item_ids_json`
- `questions_json`
- `suggested_reviews_json`
- `review_status`
- `confidence`
- `needs_review`
- `raw_codex_json`
- `created_at`
- `updated_at`

Suggested `period_type` values:
- `weekly`
- `monthly`
- `custom`

Suggested `review_status` values:
- `draft`
- `accepted`
- `ignored`
- `needs_review`

## Processing flow

### 1. Python selects candidates

Python should query SQLite first and choose bounded inputs:

- recent processed archive items
- items with matching `primary_interest` or `secondary_interests`
- items with shared `topic`, `subtopic`, or tags
- items with high `revisit_priority`
- items with strong `insight_seed`
- items not already used in a recent note

Python should avoid sending the entire archive to Codex. Candidate packets should be small, deterministic, and auditable.

### 2. Codex reads selected archive packets

Codex can receive:

- item ids
- title
- core summary
- key points
- interest classification
- topic/subtopic
- why saved
- revisit reason
- insight seed
- tags
- confidence / needs_review

Codex should not need raw images for normal synthesis. Raw media can stay out of synthesis unless a later review command explicitly needs it.

### 3. Codex returns structured JSON

For related captures, Codex returns candidate edges:

- source id
- target id
- relation type
- reason
- confidence
- needs_review

For recurring themes, Codex returns candidate themes:

- title
- summary
- included item ids
- interests/topics
- confidence
- needs_review

For periodic notes, Codex returns:

- title
- summary
- recurring themes
- related capture groups
- notable item ids
- questions
- suggested reviews
- confidence
- needs_review

### 4. Python validates and writes

Python must:

- verify every referenced archive item id exists
- reject references outside the selected candidate set unless explicitly allowed
- clamp confidence values
- normalize enum values
- store raw Codex JSON for audit
- mark uncertain output as `needs_review`
- write SQLite deterministically

Codex must not write SQLite directly.

## Proposed CLI surface

Start with commands that inspect before automating.

### Related captures

```bash
darchive related <capture-id>
darchive related <capture-id> --json
darchive related generate --limit 20
```

Expected use:
- inspect related captures for one item
- generate candidate relationships for recent archive items

### Insight notes

```bash
darchive insights
darchive insights generate --period weekly
darchive insights generate --period weekly --dry-run
darchive insights generate --period monthly
darchive insights show <insight-id>
darchive insights show <insight-id> --json
```

Expected use:
- list generated notes
- generate a weekly/monthly note from selected archive items
- inspect one note with evidence items

### Themes

Themes can start as part of `insights show`. A separate command can come later:

```bash
darchive themes
darchive themes show <theme-id>
```

Do not add Telegram output until local CLI review is useful.

## First local implementation

The first implementation is intentionally local and inspect-first:

- `darchive insights` lists locally stored draft notes.
- `darchive insights generate --period weekly --dry-run` previews the note without writing SQLite rows.
- `darchive insights generate --period weekly` writes a draft `insight_notes` row and evidence rows in `insight_note_items`.
- `darchive insights show <insight-id>` shows the note and the archive items used as evidence.

This first implementation uses validated SQLite archive rows and local graph/readiness signals. It does not call Telegram, does not send summaries, and does not include raw extracted text by default. It uses only processed archive items and excludes `needs_review` items unless explicitly requested.

## SQLite proposal

These tables are additive and do not rewrite existing archive data.

Proposed tables:

- `archive_relations`
- `recurring_themes`
- `insight_notes`
- `insight_note_items`

`insight_note_items` is useful even if note rows also store JSON, because it enables reliable joins and "show me notes that used this capture."

Suggested indexes:

- `archive_relations(source_archive_item_id)`
- `archive_relations(target_archive_item_id)`
- `archive_relations(relation_type)`
- `recurring_themes(primary_interest, theme_status)`
- `insight_notes(period_type, period_start, period_end)`
- `insight_note_items(archive_item_id)`

## Safety rules

- No destructive migrations.
- Do not rewrite existing captures or archive items.
- Do not send live Telegram messages from synthesis commands.
- Do not implement calendar, journal, task automation, or web UI in this layer.
- Keep local privacy: `.env`, `.local/`, SQLite, logs, and media stay out of git.
- Treat generated insights as drafts until reviewed or accepted.
- Prefer conservative synthesis over confident invention.
- Preserve item-level evidence for every generated theme or note.

## Product decisions to make later

These decisions should be brought back before implementation if they affect behavior:

- Should insight notes generate weekly, monthly, or only on demand?
- Should low-confidence archive items be excluded by default?
- Should `needs_review` items contribute to themes?
- Should themes be generated globally or per interest?
- Should the user be able to accept, dismiss, or edit themes?
- How aggressive should relation detection be: only strong matches, or exploratory weak links too?

Recommended defaults for first implementation:

- generate on demand only
- weekly period first
- include only processed archive items
- include `needs_review` items only if explicitly requested
- keep generated notes as `draft`
- require evidence item ids for every relation/theme/note

## Readiness implementation before synthesis

Before generating insight notes, use graph and archive readiness commands:

- `darchive interests`
- `darchive concepts`
- `darchive graph quality`
- `darchive reprocess-plan`
- read-only `darchive related <capture-id>`

These commands should show whether the archive has enough useful interests, topics, concepts, insight seeds, questions, and relation candidates for synthesis.
When `darchive reprocess-plan` finds weak or fallback-processed archive items, repair those rows before generating themes or notes. Otherwise the synthesis layer will amplify poor classification instead of building on the user's real interests.

## Later implementation goal

Build the Telegram delivery layer only after local draft review is useful.

Scope:
- extend `darchive related` with generated relation candidates after the read-only local version proves useful
- optionally add Codex-backed insight generation while keeping Python-only SQLite writes
- add Telegram commands such as `/insights` or a weekly digest only after draft notes are useful locally
- keep web UI, calendar, journal, and automation out of scope
- add focused tests and run public preflight
