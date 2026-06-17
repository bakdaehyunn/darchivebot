from __future__ import annotations

import json

from darchivebot.graph import default_graph_path, export_graph
from darchivebot.storage import ArchiveStore


def test_export_graph_writes_jsonld_from_archive_items(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:1",
        chat_id="chat",
        message_id=1,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="AI archive idea",
        caption="",
        content_kind="text",
        raw_message={"message_id": 1},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "AI archive idea",
            "core_summary": "AI archive summary",
            "key_points": ["Captures can become reusable ideas"],
            "raw_extracted_text": "AI archive idea",
            "why_saved": "Useful product direction",
            "source_language": "en",
            "tags": ["archive", "agents"],
            "primary_interest": "AI",
            "secondary_interests": ["career"],
            "topic": "personal knowledge graph",
            "subtopic": "JSON-LD export",
            "classification_reason": "about AI archive structure",
            "revisit_priority": "high",
            "revisit_reason": "future graph work",
            "insight_seed": "archives can become an interest graph",
            "confidence": 0.9,
            "needs_review": False,
        },
    )
    output_path = tmp_path / ".local" / "graph" / "darchivebot.jsonld"

    result = export_graph(store, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    graph = payload["@graph"]
    assert result["archive_items"] == 1
    assert result["nodes"] == len(graph)
    assert result["path"] == str(output_path)
    assert result["ontology_version"]
    assert result["export_version"] == 1
    assert result["export_scope"] == "lightweight_jsonld"
    assert result["source"] == "sqlite_archive_rows"
    assert result["semantic_store_equivalent"] is False
    assert result["raw_text_included"] is False
    assert payload["metadata"]["archive_items"] == 1
    assert payload["metadata"]["nodes"] == len(graph)
    assert payload["metadata"]["export_scope"] == "lightweight_jsonld"
    assert payload["@context"]["darch"] == "https://darchivebot.local/ontology#"
    assert any(node["@type"] == "darch:Capture" for node in graph)
    archive_nodes = [node for node in graph if node["@type"] == "darch:ArchiveItem"]
    assert archive_nodes[0]["title"] == "AI archive idea"
    assert "darch:rawExtractedText" not in archive_nodes[0]
    assert archive_nodes[0]["hasInterest"] == "urn:darchive:interest:ai"
    assert archive_nodes[0]["hasSecondaryInterest"] == ["urn:darchive:interest:career"]
    assert archive_nodes[0]["hasTopic"] == "urn:darchive:topic:personal-knowledge-graph"
    assert archive_nodes[0]["makesClaim"]
    assert any(node["@type"] == "darch:Claim" for node in graph)


def test_export_graph_can_include_raw_text_explicitly(tmp_path):
    store = ArchiveStore(tmp_path / "state")
    capture_id = store.add_capture(
        capture_key="chat:raw",
        chat_id="chat",
        message_id=2,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="raw text",
        caption="",
        content_kind="text",
        raw_message={"message_id": 2},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "Raw text item",
            "core_summary": "Summary only",
            "raw_extracted_text": "private raw extracted text",
            "source_language": "en",
            "primary_interest": "AI",
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    output_path = tmp_path / ".local" / "graph" / "darchivebot.jsonld"

    result = export_graph(store, output_path, include_raw_text=True)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    archive_nodes = [node for node in payload["@graph"] if node["@type"] == "darch:ArchiveItem"]
    assert result["raw_text_included"] is True
    assert archive_nodes[0]["darch:rawExtractedText"] == "private raw extracted text"


def test_default_graph_path_stays_under_local_graph(tmp_path):
    assert default_graph_path(tmp_path) == tmp_path / ".local" / "graph" / "darchivebot.jsonld"
