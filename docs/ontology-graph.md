# Ontology-native graph transition

다카이브봇의 long-term direction is a local personal interest graph that supports the Viewpoint Layer. SQLite remains the source of truth and ingestion ledger for Telegram capture state, files, processing runs, and retry status. The graph layer becomes the semantic memory for interests, topics, concepts, claims, questions, and relation candidates. The Viewpoint Layer later uses those facts for related captures, recurring themes, insight notes, and bounded Codex discussion context.

## Storage decision

Current step: embedded pyoxigraph RDF store under `.local/graph/semantic-store/`, with JSON-LD export under `.local/graph/darchivebot.jsonld` as a lightweight portable export for inspection and sharing.

Why this first:
- pyoxigraph gives a local RDF/SPARQL store without a server process.
- The store lives under `.local/` and can be rebuilt from SQLite.
- It keeps current SQLite ingestion stable.
- N-Quads can export the semantic store, while JSON-LD remains easy to inspect and regenerate from validated SQLite rows.

Later options:
- Add graph query helpers for recurring themes and related captures.
- Add richer extraction fields for verified inter-item relations after there are enough real captures to evaluate them.
- Feed the Viewpoint Layer with evidence-backed graph facts instead of broad archive summaries.

Do not switch raw capture storage away from SQLite. The graph store should be regenerated from validated archive rows until the ontology model proves stable. In normal scheduled operation, `darchive process --export-graph` refreshes the graph only after at least one capture is successfully processed.

raw extracted text is not exported or stored in the semantic graph by default. Use `darchive graph sync --include-raw-text` or `darchive graph export --include-raw-text` only when local analysis needs the full OCR/message text in graph output.

## Ontology classes

Core classes:
- `darch:Capture`: raw Telegram capture identity and source metadata.
- `darch:ArchiveItem`: interpreted archive item produced from a capture.
- `darch:Interest`: high-level interest area such as AI, career, sports.
- `darch:Topic`: topic or subtopic inside an interest.
- `darch:Concept`: reusable tag/concept mentioned by an archive item.
- `darch:Claim`: key point or claim extracted from an archive item.
- `darch:Question`: explicit unresolved question or useful follow-up question from processor output.
- `darch:RelationCandidate`: possible relation to resolve in later synthesis.
- `darch:Theme`: recurring pattern across multiple archive items.
- `darch:InsightNote`: periodic synthesis generated from selected archive items.

Future classes:
- `darch:Source`: source app/site/account when reliably detected.
- `darch:ProjectIdea`: possible project forming across captures.
- `darch:Question`: unresolved question repeated across captures.

## Ontology relationships

Current graph store relationships:
- `darch:aboutCapture`: ArchiveItem -> Capture
- `darch:hasInterest`: ArchiveItem -> primary Interest
- `darch:hasSecondaryInterest`: ArchiveItem -> secondary Interest
- `darch:hasTopic`: ArchiveItem -> Topic
- `darch:hasSubtopic`: ArchiveItem -> Topic
- `darch:mentionsConcept`: ArchiveItem -> Concept
- `darch:makesClaim`: ArchiveItem -> Claim
- `darch:asksQuestion`: ArchiveItem -> Question
- `darch:hasRelationCandidate`: ArchiveItem -> RelationCandidate

Future insight relationships:
- `darch:relatedTo`: ArchiveItem -> ArchiveItem
- `darch:supports`: Claim/ArchiveItem -> Claim/ArchiveItem
- `darch:contradicts`: Claim/ArchiveItem -> Claim/ArchiveItem
- `darch:updates`: ArchiveItem -> ArchiveItem
- `darch:partOfTheme`: ArchiveItem -> Theme
- `darch:evidenceFor`: ArchiveItem/Claim -> InsightNote
- `darch:leadsTo`: Theme/InsightNote -> ProjectIdea or Question
- `darch:revisitFor`: ArchiveItem -> Purpose/Question

## Current graph store commands

```bash
darchive graph init
darchive graph sync
darchive graph stats
darchive graph store-export
```

Default store:

```text
.local/graph/semantic-store/
```

Default N-Quads export:

```text
.local/graph/semantic-store.nq
```

## Portable JSON-LD export

```bash
darchive graph export
```

Default output:

```text
.local/graph/darchivebot.jsonld
```

The output is local runtime data. It must stay out of git through the existing `.local/` ignore rule.

This JSON-LD file is not the canonical semantic graph store and is not a complete backup of every RDF fact. It is a lightweight export of archive items and their main relationships. Use `darchive graph store-export` when the goal is to dump the current semantic store facts.

Optional:

```bash
darchive graph sync --include-raw-text
darchive graph sync --limit 20 --json
darchive graph store-export --output /tmp/darchivebot.nq
darchive graph export --output /tmp/darchivebot.jsonld
darchive graph export --limit 20 --json
darchive graph export --include-raw-text
```

The graph file includes export metadata:

```json
{
  "metadata": {
    "@type": "darch:GraphExport",
    "ontology_version": "2026-06-08",
    "export_version": 1,
    "export_scope": "lightweight_jsonld",
    "source": "sqlite_archive_rows",
    "semantic_store_equivalent": false,
    "generated_at": "<iso-datetime>",
    "archive_items": 12,
    "nodes": 84,
    "raw_text_included": false
  }
}
```

## Sample capture-to-graph mapping

Archive item:

```text
title: AI 이후 FDE 채용 증가에 대한 스레드
primary_interest: AI
secondary_interests: career
topic: agents
tags: hiring, field-engineering
key_points:
- AI 제품 확산 이후 FDE 역할 수요가 늘고 있다.
- 기술 이해와 고객 문제 해결을 함께 요구한다.
```

Lightweight JSON-LD shape:

```json
{
  "@id": "urn:darchive:archive-item:<archive-id>",
  "@type": "darch:ArchiveItem",
  "title": "AI 이후 FDE 채용 증가에 대한 스레드",
  "aboutCapture": "urn:darchive:capture:<capture-id>",
  "hasInterest": "urn:darchive:interest:ai",
  "hasSecondaryInterest": ["urn:darchive:interest:career"],
  "hasTopic": "urn:darchive:topic:agents",
  "mentionsConcept": [
    "urn:darchive:concept:hiring",
    "urn:darchive:concept:field-engineering"
  ],
  "makesClaim": [
    "urn:darchive:claim:<archive-id>-1",
    "urn:darchive:claim:<archive-id>-2"
  ]
}
```

## Transition path

1. Keep SQLite as source of truth for ingestion and processing state.
2. Rebuild the pyoxigraph semantic store from validated archive rows.
3. Keep portable JSON-LD/N-Quads export available:
   - `darchive graph sync`
   - `darchive graph stats`
   - `darchive graph store-export`
   - `darchive graph export`
   - `darchive graph query`
   - `darchive concepts`
   - `darchive interests`
   - `darchive related <capture-id>`
4. Use graph facts to select candidates for related captures and recurring themes.
5. Build graph/readiness commands before insight synthesis.
6. Add higher-level Viewpoint Layer commands only after the graph has enough real captures to make relation discovery useful.

## Safety rules

- No destructive SQLite migration.
- Do not rewrite existing captures or archive items.
- Do not store graph output or graph store files in git.
- Codex must not write graph files or graph store files directly.
- Python writes graph store facts from validated SQLite rows.
- Raw extracted text is omitted from graph store and export unless explicitly requested.
- No paid external services.
- No live Telegram sending from graph commands.
