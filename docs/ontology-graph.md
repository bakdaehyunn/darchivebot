# Ontology-native graph transition

다카이브봇의 long-term direction is a local personal interest graph. SQLite remains the source of truth and ingestion ledger for Telegram capture state, files, processing runs, and retry status. The graph layer becomes the semantic read model for interests, topics, concepts, claims, relations, themes, and insight notes.

## Storage decision

First step: JSON-LD export under `.local/graph/darchivebot.jsonld`.

Why this first:
- JSON-LD is ontology-shaped and can later move to RDF/SPARQL tooling.
- It does not add a server, paid service, or runtime dependency.
- It keeps current SQLite ingestion stable.
- It is easy to inspect, diff locally, and regenerate.

Later options:
- `rdflib`: good for local RDF parsing and simple SPARQL-like work in Python.
- `pyoxigraph`: stronger embedded RDF/SPARQL store if the graph becomes larger or query-heavy.

Do not switch raw capture storage away from SQLite. The graph should be regenerated from validated archive rows until the ontology model proves stable.

## Ontology classes

Core classes:
- `darch:Capture`: raw Telegram capture identity and source metadata.
- `darch:ArchiveItem`: interpreted archive item produced from a capture.
- `darch:Interest`: high-level interest area such as AI, career, sports.
- `darch:Topic`: topic or subtopic inside an interest.
- `darch:Concept`: reusable tag/concept mentioned by an archive item.
- `darch:Claim`: key point or claim extracted from an archive item.
- `darch:Theme`: recurring pattern across multiple archive items.
- `darch:InsightNote`: periodic synthesis generated from selected archive items.

Future classes:
- `darch:Source`: source app/site/account when reliably detected.
- `darch:ProjectIdea`: possible project forming across captures.
- `darch:Question`: unresolved question repeated across captures.

## Ontology relationships

Current graph export relationships:
- `darch:aboutCapture`: ArchiveItem -> Capture
- `darch:hasInterest`: ArchiveItem -> primary Interest
- `darch:hasSecondaryInterest`: ArchiveItem -> secondary Interest
- `darch:hasTopic`: ArchiveItem -> Topic
- `darch:hasSubtopic`: ArchiveItem -> Topic
- `darch:mentionsConcept`: ArchiveItem -> Concept
- `darch:makesClaim`: ArchiveItem -> Claim

Future insight relationships:
- `darch:relatedTo`: ArchiveItem -> ArchiveItem
- `darch:supports`: Claim/ArchiveItem -> Claim/ArchiveItem
- `darch:contradicts`: Claim/ArchiveItem -> Claim/ArchiveItem
- `darch:updates`: ArchiveItem -> ArchiveItem
- `darch:partOfTheme`: ArchiveItem -> Theme
- `darch:evidenceFor`: ArchiveItem/Claim -> InsightNote
- `darch:leadsTo`: Theme/InsightNote -> ProjectIdea or Question
- `darch:revisitFor`: ArchiveItem -> Purpose/Question

## Current export command

```bash
darchive graph export
```

Default output:

```text
.local/graph/darchivebot.jsonld
```

The output is local runtime data. It must stay out of git through the existing `.local/` ignore rule.

Optional:

```bash
darchive graph export --output /tmp/darchivebot.jsonld
darchive graph export --limit 20 --json
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

JSON-LD shape:

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
2. Export validated archive items to JSON-LD graph facts.
3. Add local graph inspection commands after export is useful:
   - `darchive graph export`
   - `darchive graph query`
   - `darchive concepts`
   - `darchive interests`
   - `darchive related <capture-id>`
4. Use graph facts to select candidates for related captures and recurring themes.
5. Move to `rdflib` or `pyoxigraph` only when file export is not enough for local querying.

## Safety rules

- No destructive SQLite migration.
- Do not rewrite existing captures or archive items.
- Do not store graph output in git.
- Codex must not write graph files directly.
- Python writes graph files from validated SQLite rows.
- No paid external services.
- No live Telegram sending from graph commands.
