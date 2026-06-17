# Viewpoint Layer

The Viewpoint Layer is the long-term product layer for 다카이브봇.

다카이브봇 should not stop at storing captures. The final goal is to make saved captures usable as personal viewpoint material: what the user keeps noticing, what questions keep returning, what topics are becoming important, and what older captures should come back into a new discussion.

The Viewpoint Layer sits above the archive and semantic graph. It does not replace them. It uses their validated data to help Codex discuss the user's own saved material from the user's point of view.

## Layer stack

```text
Capture Layer
  -> Telegram messages, screenshots, photos, documents, and local media files

Archive Layer
  -> SQLite source of truth for captures, files, extracted text, archive items, and processing state

Semantic Graph Layer
  -> interests, topics, concepts, claims, questions, and relation candidates generated from validated archive rows

Viewpoint Layer
  -> related captures, recurring themes, unresolved questions, project seeds, periodic insight notes, and Codex discussion context
```

## User problem

The user is not only saving things to find them later. The user is trying to turn scattered interest into reusable thinking material.

The Viewpoint Layer should answer:

- What do I keep saving?
- Which saved captures belong together?
- What questions or concerns are becoming repeated?
- What project idea, decision, habit, or writing direction is forming?
- What should Codex know about my current interests before discussing a topic with me?

The layer must preserve each capture as evidence. It should not collapse the archive into one generic summary.

## What it needs from lower layers

From the Capture Layer:
- original Telegram source metadata
- local media paths
- message/caption context

From the Archive Layer:
- title
- core summary
- key points
- interests and topics
- why saved
- revisit priority and reason
- insight seed
- confidence and review state

From the Semantic Graph Layer:
- interest nodes
- topic nodes
- concept nodes
- claim nodes
- question nodes
- relation candidates

Raw extracted text should stay out of normal Viewpoint Layer inputs by default. It can be included only through explicit local review commands when the user needs deeper analysis.

## Staged roadmap

### Stage 1: graph and archive readiness

Goal: make the existing archive inspectable before generating insights.

First commands should answer:
- Which interests exist?
- Which concepts appear often?
- Which captures are weakly classified?
- Which items were processed by fallback logic?
- Which captures are missing topics, insight seeds, or useful graph facts?

This stage should be local, read-only, and safe. It should not rewrite existing archive items.

### Stage 2: related capture discovery

Goal: show which saved items connect to each other.

Start with conservative local matching from interests, topics, concepts, and relation candidates. Codex-based relation generation can come later after the local signals are trustworthy.

Useful output:
- source capture
- related capture
- relation reason
- shared interest/topic/concept
- confidence
- needs review flag

### Stage 3: recurring themes

Goal: identify patterns that appear across multiple captures.

Themes should be evidence-backed. Every theme should point back to the archive items that support it.

Examples:
- a repeated interest in agent workflows
- a recurring concern about career direction
- a project idea forming from several saved screenshots
- a writing topic appearing across multiple captures

### Stage 4: periodic insight notes

Goal: turn a time window into a readable note.

Weekly or monthly notes should summarize:
- repeated themes
- notable captures
- unresolved questions
- useful items to revisit
- possible project or writing seeds

Insight notes should start as drafts. They should not become automation, calendar entries, or Telegram summaries until local review is useful.

### Stage 5: Codex discussion context

Goal: let Codex use the user's archive as discussion context.

When the user asks Codex about a topic, 다카이브봇 should be able to provide bounded context:
- relevant captures
- related themes
- prior questions
- recurring interests
- evidence items

This is the actual Viewpoint Layer payoff: Codex can discuss new questions with awareness of what the user has been saving and thinking about.

## First implementation phase

The next practical implementation phase should be graph and archive readiness.

Recommended scope:
- add `darchive interests`
- add `darchive concepts`
- add `darchive graph quality`
- add a read-only first version of `darchive related <capture-id>`
- add `darchive reprocess-plan` for weak/fallback archive items
- keep all commands local and inspect-first
- do not generate insight notes yet
- do not send Telegram summaries
- do not rewrite existing SQLite rows

This phase gives the user a way to see whether the archive is strong enough for synthesis.

Current command shape:

```bash
darchive interests
darchive interests --json
darchive concepts
darchive concepts --json
darchive graph quality
darchive graph quality --json
darchive reprocess-plan
darchive reprocess-plan --json
darchive reprocess --capture-id <capture-id> --dry-run
darchive related <capture-id>
darchive related <capture-id> --json
```

These commands are local inspection commands. They do not call Codex, create insight notes, send Telegram messages, or rewrite existing archive rows.

`darchive reprocess-plan` is the quality-repair bridge before synthesis. It lists captures whose archive rows are too weak for reliable Viewpoint Layer work, including fallback-processed rows, missing/unknown interests, missing topics, missing key points, missing insight seeds, missing questions, missing relation candidates, low confidence, and `needs_review` rows. `darchive reprocess --dry-run` previews selected candidates only; actual archive rewrites should remain a separate, explicit implementation step.

## Deferred work

Do not start with:
- weekly/monthly insight generation
- Codex-generated relation edges
- Telegram summaries
- calendar, journal, or task automation
- web UI
- destructive migrations

Those should wait until the archive has enough reliable capture data and the graph/readiness commands show useful signals.

## Safety rules

- SQLite remains the operational source of truth.
- The semantic graph remains a generated meaning layer.
- Codex returns structured JSON only; Python owns validation and writes.
- Raw text is excluded from normal graph and viewpoint outputs unless explicitly requested.
- Every generated relation, theme, or note must preserve evidence item ids.
- Generated insights start as drafts, not facts.
