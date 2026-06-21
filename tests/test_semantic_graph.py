from __future__ import annotations

from darchivebot.semantic_graph import (
    default_semantic_export_path,
    default_semantic_store_path,
    export_semantic_store,
    semantic_store_stats,
    sync_semantic_store,
)
from darchivebot.storage import ArchiveStore


def test_sync_semantic_store_rebuilds_idempotent_rdf_store(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    add_archive_item(store)
    graph_path = tmp_path / ".local" / "graph" / "semantic-store"

    first = sync_semantic_store(store, graph_path)
    second = sync_semantic_store(store, graph_path)

    assert first["synced_archive_items"] == 1
    assert second["synced_archive_items"] == 1
    assert first["quads"] == second["quads"]
    assert second["archive_items"] == 1
    assert second["captures"] == 1
    assert second["interests"] == 2
    assert second["topics"] == 2
    assert second["concepts"] == 2
    assert second["claims"] == 2
    assert second["questions"] == 1
    assert second["relation_candidates"] == 1


def test_semantic_store_omits_raw_text_by_default_and_can_include_it(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    add_archive_item(store)
    graph_path = tmp_path / ".local" / "graph" / "semantic-store"

    default_stats = sync_semantic_store(store, graph_path)
    raw_stats = sync_semantic_store(store, graph_path, include_raw_text=True)

    assert default_stats["raw_text_included"] is False
    assert raw_stats["raw_text_included"] is True


def test_semantic_store_export_writes_nquads(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    add_archive_item(store)
    graph_path = default_semantic_store_path(tmp_path)
    export_path = default_semantic_export_path(tmp_path)

    sync_semantic_store(store, graph_path)
    result = export_semantic_store(graph_path, export_path)

    assert result["export_path"] == str(export_path)
    assert export_path.exists()
    text = export_path.read_text(encoding="utf-8")
    assert "darchivebot.local/ontology#ArchiveItem" in text
    assert "darchivebot.local/graph/semantic" in text


def test_semantic_store_prefers_normalized_questions_and_relation_candidates(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = add_archive_item(store)
    with store.connect() as conn:
        conn.execute(
            """
            UPDATE archive_items
            SET raw_codex_json = ?
            WHERE capture_id = ?
            """,
            (
                '{"questions":["raw stale question"],"relation_candidates":["raw stale relation"]}',
                capture_id,
            ),
        )
    graph_path = default_semantic_store_path(tmp_path)
    export_path = default_semantic_export_path(tmp_path)

    sync_semantic_store(store, graph_path)
    export_semantic_store(graph_path, export_path)

    text = export_path.read_text(encoding="utf-8")
    assert "How should Codex use this viewpoint later?" in text
    assert "related to ontology transition" in text
    assert "raw stale question" not in text
    assert "raw stale relation" not in text


def test_semantic_store_stats_handles_missing_store(tmp_path):
    stats = semantic_store_stats(tmp_path / ".local" / "graph" / "missing-store")

    assert stats["exists"] is False
    assert stats["quads"] == 0


def add_archive_item(store: ArchiveStore) -> str:
    capture_id = store.add_capture(
        capture_key="chat:semantic",
        chat_id="chat",
        message_id=10,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="Semantic graph idea",
        caption="",
        content_kind="text",
        raw_message={"message_id": 10},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "Semantic graph idea",
            "core_summary": "A capture can become semantic memory.",
            "key_points": ["SQLite stays operational", "Graph stores meaning"],
            "raw_extracted_text": "private raw text",
            "why_saved": "Useful direction for personal archive memory",
            "source_language": "en",
            "tags": ["graph", "memory"],
            "primary_interest": "AI",
            "secondary_interests": ["personal ideas"],
            "topic": "personal interest graph",
            "subtopic": "semantic store",
            "classification_reason": "about graph-native archive structure",
            "revisit_priority": "high",
            "revisit_reason": "future architecture",
            "insight_seed": "captures can become viewpoint-aware memory",
            "questions": ["How should Codex use this viewpoint later?"],
            "relation_candidates": ["related to ontology transition"],
            "confidence": 0.9,
            "needs_review": False,
        },
    )
    return capture_id
