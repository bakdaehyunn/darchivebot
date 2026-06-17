from __future__ import annotations

import json

from darchivebot import cli
from darchivebot.cli import main
from darchivebot.config import Settings
from darchivebot.storage import ArchiveStore


def test_doctor_offline_allows_missing_telegram_token(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("DARCHIVE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DARCHIVE_MEDIA_DIR", str(tmp_path / "captures"))
    monkeypatch.setenv("DARCHIVE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DARCHIVE_CODEX_BIN", "python3")
    monkeypatch.setenv("DARCHIVE_CODEX_ENABLED", "false")

    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN is missing" in output
    assert "sqlite:" in output


def test_setup_cmd_writes_env_without_printing_secret(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    settings = make_cli_settings(tmp_path)
    monkeypatch.setattr(cli, "DEFAULT_ENV_FILE", env_file)
    monkeypatch.setattr(cli, "get_settings", lambda: make_cli_settings(tmp_path, token="secret-token", chat_ids=("-100123",)))
    monkeypatch.setattr(cli, "run_doctor", lambda settings, store, online=False: (0, "[OK] doctor"))

    assert (
        cli.setup_cmd(
            settings,
            dry_run=False,
            non_interactive=True,
            telegram_bot_token="secret-token",
            telegram_chat_id="-100123",
            telegram_admin_user_id="42",
            allow_all_chats=False,
            install_launchd=False,
        )
        == 0
    )

    assert "secret-token" in env_file.read_text(encoding="utf-8")
    assert "secret-token" not in capsys.readouterr().out


def test_send_test_requires_exactly_one_target(capsys):
    settings = make_cli_settings(__import__("pathlib").Path("/tmp"), token="token", chat_ids=("123",))

    assert cli.send_test_cmd(settings, chat_id=None, use_registered=False, use_allowed=False, dry_run=True) == 2
    assert "choose exactly one target" in capsys.readouterr().out

    assert cli.send_test_cmd(settings, chat_id=None, use_registered=False, use_allowed=True, dry_run=True) == 0
    assert "would send test message to ***" in capsys.readouterr().out


def test_rooms_reports_registered_room(tmp_path, capsys, monkeypatch):
    settings = make_cli_settings(tmp_path, chat_ids=())
    settings.state_dir.mkdir(parents=True)
    (settings.state_dir / "telegram_rooms.json").write_text(
        json.dumps({"darchive_chat_id": "-100123", "darchive_chat_title": "archive"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["rooms"]) == 0
    output = capsys.readouterr().out
    assert "darchive_chat_id=***0123" in output
    assert "allowed=yes" in output


def test_pending_shows_dry_run_processor_context(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path, codex_enabled=True)
    store = ArchiveStore(settings.state_dir)
    store.add_capture(
        capture_key="chat:1",
        chat_id="chat",
        message_id=1,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="관심 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 1},
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["pending"]) == 0
    output = capsys.readouterr().out
    assert "dry-run processor=codex kind=text files=0" in output
    assert "관심 글" in output


def test_list_shows_file_and_archive_status(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = store.add_capture(
        capture_key="chat:2",
        chat_id="chat",
        message_id=2,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="관심 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 2},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "정리된 제목",
            "core_summary": "스크린샷 안의 핵심 요약",
            "key_points": ["핵심 1"],
            "context": "screenshot",
            "raw_extracted_text": "관심 글",
            "why_saved": "참고할 만한 내용",
            "source_language": "ko",
            "tags": [],
            "primary_interest": "AI",
            "secondary_interests": ["career"],
            "topic": "agents",
            "subtopic": "personal archive",
            "classification_reason": "AI archive workflow",
            "revisit_priority": "high",
            "revisit_reason": "제품 방향에 참고",
            "insight_seed": "AI와 개인 아카이브 연결",
            "dates_mentioned": [],
            "people_mentioned": [],
            "action_candidates": [],
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["list"]) == 0
    output = capsys.readouterr().out
    assert "files=none" in output
    assert "archive=archived" in output
    assert "interest=AI topic=agents" in output
    assert "정리된 제목" in output


def test_list_filters_by_interest(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = store.add_capture(
        capture_key="chat:21",
        chat_id="chat",
        message_id=21,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="커리어 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 21},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "커리어 글",
            "core_summary": "커리어 요약",
            "raw_extracted_text": "커리어 글",
            "source_language": "ko",
            "primary_interest": "career",
            "secondary_interests": ["AI"],
            "topic": "portfolio",
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["list", "--interest", "AI"]) == 0
    output = capsys.readouterr().out
    assert capture_id in output
    assert "interest=career topic=portfolio" in output


def test_interests_and_concepts_inspect_archive_distribution(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    first_id = add_archive_item(
        store,
        message_id=41,
        title="AI archive",
        primary_interest="AI",
        secondary_interests=["career"],
        topic="agents",
        tags=["graph", "agents"],
    )
    add_archive_item(
        store,
        message_id=42,
        title="Career archive",
        primary_interest="career",
        secondary_interests=["AI"],
        topic="portfolio",
        tags=["career", "agents"],
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["interests"]) == 0
    interests_output = capsys.readouterr().out
    assert "archive_items=2" in interests_output
    assert "AI\ttotal=2 primary=1 secondary=1" in interests_output
    assert "career\ttotal=2 primary=1 secondary=1" in interests_output

    assert main(["concepts", "--json"]) == 0
    concepts = json.loads(capsys.readouterr().out)
    assert concepts["archive_items"] == 2
    assert {"concept": "agents", "count": 2} in concepts["concepts"]
    assert first_id


def test_graph_quality_reports_readiness_issues(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    add_archive_item(
        store,
        message_id=43,
        title="Fallback archive",
        primary_interest="other/unknown",
        secondary_interests=[],
        topic="",
        tags=[],
        classification_reason="local fallback did not classify the capture semantically",
        confidence=0.25,
        needs_review=True,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["graph", "quality", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    issues = {item["name"]: item for item in result["issues"]}
    assert result["archive_items"] == 1
    assert result["ready_for_synthesis"] is False
    assert issues["unknown_primary_interest"]["count"] == 1
    assert issues["fallback_processed"]["count"] == 1
    assert issues["missing_topic"]["count"] == 1


def test_reprocess_plan_lists_weak_candidates_with_reasons_and_history(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_archive_item(
        store,
        message_id=47,
        title="Weak fallback archive",
        primary_interest="other/unknown",
        secondary_interests=[],
        topic="",
        tags=[],
        classification_reason="local fallback did not classify the capture semantically",
        confidence=0.25,
        needs_review=True,
        key_points=[],
        insight_seed="",
    )
    run_id = store.start_processing_run(capture_id=capture_id, processor="basic")
    store.finish_processing_run(run_id=run_id, status="processed")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["reprocess-plan", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["candidate_count"] == 1
    candidate = result["candidates"][0]
    reason_names = {item["name"] for item in candidate["candidate_reasons"]}
    assert candidate["capture_id"] == capture_id
    assert candidate["current"]["primary_interest"] == "other/unknown"
    assert candidate["current"]["topic"] == ""
    assert candidate["current"]["confidence"] == 0.25
    assert candidate["current"]["needs_review"] is True
    assert {
        "unknown_primary_interest",
        "missing_topic",
        "missing_insight_seed",
        "missing_key_points",
        "missing_concepts",
        "needs_review",
        "low_confidence",
        "fallback_processed",
        "missing_questions",
        "missing_relation_candidates",
    }.issubset(reason_names)
    assert candidate["processor_history_count"] == 1
    assert candidate["processor_history"][0]["processor"] == "basic"
    assert candidate["processor_history"][0]["status"] == "processed"


def test_reprocess_plan_filters_candidates(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    fallback_id = add_archive_item(
        store,
        message_id=48,
        title="Fallback candidate",
        primary_interest="other/unknown",
        secondary_interests=[],
        topic="",
        tags=[],
        classification_reason="local fallback",
        confidence=0.3,
        needs_review=True,
    )
    add_archive_item(
        store,
        message_id=49,
        title="Topic missing only",
        primary_interest="AI",
        secondary_interests=[],
        topic="",
        tags=["agents"],
        confidence=0.8,
        needs_review=False,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["reprocess-plan", "--fallback-only", "--json"]) == 0
    fallback_result = json.loads(capsys.readouterr().out)
    assert [item["capture_id"] for item in fallback_result["candidates"]] == [fallback_id]

    assert main(["reprocess-plan", "--issue", "missing_topic", "--json"]) == 0
    topic_result = json.loads(capsys.readouterr().out)
    assert topic_result["candidate_count"] == 2

    assert main(["reprocess-plan", "--capture-id", fallback_id, "--json"]) == 0
    capture_result = json.loads(capsys.readouterr().out)
    assert capture_result["candidate_count"] == 1
    assert capture_result["candidates"][0]["capture_id"] == fallback_id


def test_reprocess_dry_run_does_not_change_archive_rows(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_archive_item(
        store,
        message_id=50,
        title="Dry run candidate",
        primary_interest="other/unknown",
        secondary_interests=[],
        topic="",
        tags=[],
        classification_reason="local fallback",
        confidence=0.2,
        needs_review=True,
    )
    before = dict(store.get_archive_item(capture_id))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["reprocess", "--capture-id", capture_id, "--dry-run", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)
    after = dict(store.get_archive_item(capture_id))
    assert result["dry_run"] is True
    assert result["candidate_count"] == 1
    assert result["would_reprocess"][0]["capture_id"] == capture_id
    assert "No SQLite rows were changed" in result["message"]
    assert after == before


def test_reprocess_requires_capture_id_for_actual_rewrites(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["reprocess", "--json"]) == 2

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert "--capture-id" in result["message"]


def test_reprocess_selected_capture_refreshes_graph_after_success(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path, codex_enabled=False)
    store = ArchiveStore(settings.state_dir)
    capture_id = add_archive_item(
        store,
        message_id=51,
        title="Selected actual",
        primary_interest="other/unknown",
        secondary_interests=[],
        topic="",
        tags=[],
        classification_reason="local fallback",
        confidence=0.2,
        needs_review=True,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["reprocess", "--capture-id", capture_id, "--no-codex", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)
    after = dict(store.get_archive_item(capture_id))
    assert result["results"][0]["capture_id"] == capture_id
    assert result["results"][0]["status"] == "processed"
    assert result["semantic_graph"]["synced_archive_items"] == 1
    assert result["jsonld_graph"]["archive_items"] == 1
    assert after["core_summary"] == "Selected actual"
    assert after["primary_interest"] == "other/unknown"
    assert (tmp_path / ".local" / "graph" / "semantic-store").exists()
    assert (tmp_path / ".local" / "graph" / "darchivebot.jsonld").exists()


def test_related_uses_read_only_shared_archive_signals(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    source_id = add_archive_item(
        store,
        message_id=44,
        title="Agent memory",
        primary_interest="AI",
        secondary_interests=["career"],
        topic="agents",
        tags=["graph", "memory"],
    )
    related_id = add_archive_item(
        store,
        message_id=45,
        title="Agent workflow",
        primary_interest="AI",
        secondary_interests=[],
        topic="agents",
        tags=["graph", "workflow"],
    )
    add_archive_item(
        store,
        message_id=46,
        title="Unrelated",
        primary_interest="sports",
        secondary_interests=[],
        topic="baseball",
        tags=["pitching"],
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["related", source_id, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["capture_id"] == source_id
    assert [item["capture_id"] for item in result["related"]] == [related_id]
    assert result["related"][0]["score"] > 0
    assert "agents" in result["related"][0]["shared_topics"]
    assert "graph" in result["related"][0]["shared_concepts"]


def test_insights_generate_dry_run_uses_processed_review_ready_items_without_raw_text(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    first_id = add_archive_item(
        store,
        message_id=51,
        title="Agent archive direction",
        primary_interest="AI",
        secondary_interests=["career"],
        topic="agents",
        tags=["graph", "memory"],
        raw_text="SECRET RAW TEXT ONE",
    )
    second_id = add_archive_item(
        store,
        message_id=52,
        title="Agent workflow direction",
        primary_interest="AI",
        secondary_interests=["technology"],
        topic="agents",
        tags=["graph", "workflow"],
        raw_text="SECRET RAW TEXT TWO",
    )
    review_id = add_archive_item(
        store,
        message_id=53,
        title="Needs review archive",
        primary_interest="AI",
        secondary_interests=[],
        topic="agents",
        tags=["review"],
        needs_review=True,
        raw_text="SECRET REVIEW TEXT",
    )
    for capture_id in (first_id, second_id, review_id):
        store.mark_capture_status(capture_id, "processed")
    first_archive_id = store.get_archive_item(first_id)["id"]
    second_archive_id = store.get_archive_item(second_id)["id"]
    review_archive_id = store.get_archive_item(review_id)["id"]
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["insights", "generate", "--period", "weekly", "--dry-run", "--json"]) == 0

    output = capsys.readouterr().out
    result = json.loads(output)
    note = result["would_create"]
    assert result["status"] == "dry-run"
    assert note["review_status"] == "draft"
    assert note["raw_codex_json"]["raw_text_included"] is False
    assert set(note["notable_archive_item_ids"]) == {first_archive_id, second_archive_id}
    assert review_archive_id not in note["notable_archive_item_ids"]
    assert "SECRET RAW TEXT" not in output


def test_insights_generate_creates_lists_and_shows_draft_with_evidence(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    first_id = add_archive_item(
        store,
        message_id=54,
        title="Personal graph memory",
        primary_interest="AI",
        secondary_interests=["career"],
        topic="agents",
        tags=["graph", "memory"],
    )
    second_id = add_archive_item(
        store,
        message_id=55,
        title="Personal graph workflow",
        primary_interest="AI",
        secondary_interests=["technology"],
        topic="agents",
        tags=["graph", "workflow"],
    )
    for capture_id in (first_id, second_id):
        store.mark_capture_status(capture_id, "processed")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["insights", "generate", "--period", "weekly", "--json"]) == 0

    generated = json.loads(capsys.readouterr().out)
    insight_id = generated["insight_id"]
    assert generated["status"] == "created"
    assert generated["note"]["review_status"] == "draft"
    assert len(generated["note"]["notable_archive_item_ids"]) == 2

    assert main(["insights"]) == 0
    list_output = capsys.readouterr().out
    assert insight_id in list_output
    assert "draft" in list_output
    assert "evidence=2" in list_output

    assert main(["insights", "show", insight_id, "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["id"] == insight_id
    assert shown["review_status"] == "draft"
    assert shown["evidence_count"] == 2
    assert {item["capture_status"] for item in shown["evidence_items"]} == {"processed"}
    assert all(item["archive_item_id"] for item in shown["evidence_items"])
    assert "raw_extracted_text" not in json.dumps(shown, ensure_ascii=False)


def test_insights_generate_fails_safely_when_archive_quality_is_too_low(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    weak_id = add_archive_item(
        store,
        message_id=56,
        title="Weak archive",
        primary_interest="other/unknown",
        secondary_interests=[],
        topic="",
        tags=[],
        confidence=0.2,
        needs_review=True,
    )
    store.mark_capture_status(weak_id, "processed")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["insights", "generate", "--period", "weekly", "--dry-run", "--json"]) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "not_enough_evidence"
    assert result["eligible_count"] == 0
    assert "reprocess-plan" in result["next_step"]
    assert store.list_insight_notes() == []


def test_show_displays_structured_archive_item(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = store.add_capture(
        capture_key="chat:22",
        chat_id="chat",
        message_id=22,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="",
        caption="",
        content_kind="photo",
        raw_message={"message_id": 22},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "스크린샷 제목",
            "core_summary": "이미지 안의 실제 핵심",
            "key_points": ["중요한 주장"],
            "context": "social post screenshot",
            "raw_extracted_text": "보이는 텍스트",
            "why_saved": "나중에 참고할 아이디어",
            "source_language": "ko",
            "tags": ["idea"],
            "primary_interest": "AI",
            "secondary_interests": ["career", "technology"],
            "topic": "agents",
            "subtopic": "archive workflow",
            "classification_reason": "agent-based archive idea",
            "revisit_priority": "high",
            "revisit_reason": "다카이브봇 제품 방향과 연결됨",
            "insight_seed": "captures can become agent-readable knowledge",
            "dates_mentioned": [],
            "people_mentioned": [],
            "action_candidates": [],
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["show", capture_id]) == 0
    output = capsys.readouterr().out
    assert "archive_title: 스크린샷 제목" in output
    assert "core_summary: 이미지 안의 실제 핵심" in output
    assert "key_point: 중요한 주장" in output
    assert "why_saved: 나중에 참고할 아이디어" in output
    assert "primary_interest: AI" in output
    assert "secondary_interests: career, technology" in output
    assert "topic: agents" in output
    assert "classification_reason: agent-based archive idea" in output
    assert "revisit_priority: high" in output
    assert "insight_seed: captures can become agent-readable knowledge" in output


def test_process_prints_progress(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path, codex_enabled=False)
    store = ArchiveStore(settings.state_dir)
    store.add_capture(
        capture_key="chat:3",
        chat_id="chat",
        message_id=3,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="처리할 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 3},
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["process", "--no-codex"]) == 0
    output = capsys.readouterr().out
    assert "[process:start]" in output
    assert "[process:done]" in output
    assert "elapsed=" in output


def test_graph_export_writes_jsonld_under_local_graph(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = store.add_capture(
        capture_key="chat:31",
        chat_id="chat",
        message_id=31,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="그래프 글",
        caption="",
        content_kind="text",
        raw_message={"message_id": 31},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "그래프 글",
            "core_summary": "그래프 요약",
            "raw_extracted_text": "그래프 글",
            "source_language": "ko",
            "primary_interest": "AI",
            "secondary_interests": ["technology"],
            "topic": "ontology graph",
            "tags": ["graph"],
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["graph", "export"]) == 0

    output = capsys.readouterr().out
    graph_path = tmp_path / ".local" / "graph" / "darchivebot.jsonld"
    assert "exported 1 archive items" in output
    assert graph_path.exists()
    assert "darch:ArchiveItem" in graph_path.read_text(encoding="utf-8")


def test_graph_export_json_omits_raw_text_by_default(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = store.add_capture(
        capture_key="chat:32",
        chat_id="chat",
        message_id=32,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="민감한 원문",
        caption="",
        content_kind="text",
        raw_message={"message_id": 32},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "그래프 프라이버시",
            "core_summary": "요약만 내보냄",
            "raw_extracted_text": "민감한 원문 전체",
            "source_language": "ko",
            "primary_interest": "AI",
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["graph", "export", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)
    graph_path = tmp_path / ".local" / "graph" / "darchivebot.jsonld"
    graph_text = graph_path.read_text(encoding="utf-8")
    assert result["raw_text_included"] is False
    assert "darch:rawExtractedText" not in graph_text
    assert "민감한 원문 전체" not in graph_text


def test_graph_init_creates_semantic_store(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["graph", "init"]) == 0

    output = capsys.readouterr().out
    semantic_store_path = tmp_path / ".local" / "graph" / "semantic-store"
    assert "initialized semantic graph store" in output
    assert semantic_store_path.exists()


def test_graph_sync_stats_and_store_export_use_semantic_store(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    capture_id = store.add_capture(
        capture_key="chat:33",
        chat_id="chat",
        message_id=33,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="그래프 통계",
        caption="",
        content_kind="text",
        raw_message={"message_id": 33},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": "그래프 통계",
            "core_summary": "통계 요약",
            "source_language": "ko",
            "primary_interest": "AI",
            "confidence": 0.8,
            "needs_review": False,
        },
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["graph", "sync"]) == 0
    sync_output = capsys.readouterr().out
    assert "synced 1 archive items" in sync_output
    semantic_store_path = tmp_path / ".local" / "graph" / "semantic-store"
    assert semantic_store_path.exists()

    assert main(["graph", "store-export"]) == 0
    store_export_output = capsys.readouterr().out
    semantic_export_path = tmp_path / ".local" / "graph" / "semantic-store.nq"
    assert "exported semantic graph store" in store_export_output
    assert semantic_export_path.exists()

    capsys.readouterr()
    assert main(["graph", "stats"]) == 0

    output = capsys.readouterr().out
    assert "archive_items=1" in output
    assert "quads=" in output
    assert "raw_text_included=false" in output


def test_process_export_graph_refreshes_after_successful_processing(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path, codex_enabled=False)
    store = ArchiveStore(settings.state_dir)
    store.add_capture(
        capture_key="chat:34",
        chat_id="chat",
        message_id=34,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text="처리 후 그래프",
        caption="",
        content_kind="text",
        raw_message={"message_id": 34},
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["process", "--no-codex", "--export-graph"]) == 0

    output = capsys.readouterr().out
    semantic_store_path = tmp_path / ".local" / "graph" / "semantic-store"
    jsonld_graph_path = tmp_path / ".local" / "graph" / "darchivebot.jsonld"
    assert "semantic graph synced 1 archive items" in output
    assert "jsonld graph exported 1 archive items" in output
    assert semantic_store_path.exists()
    assert jsonld_graph_path.exists()
    payload = json.loads(jsonld_graph_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["archive_items"] == 1


def test_process_export_graph_does_not_refresh_when_nothing_processed(tmp_path, monkeypatch, capsys):
    settings = make_cli_settings(tmp_path, codex_enabled=False)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert main(["process", "--no-codex", "--export-graph"]) == 0

    output = capsys.readouterr().out
    semantic_store_path = tmp_path / ".local" / "graph" / "semantic-store"
    jsonld_graph_path = tmp_path / ".local" / "graph" / "darchivebot.jsonld"
    assert output.strip() == "nothing to process"
    assert not semantic_store_path.exists()
    assert not jsonld_graph_path.exists()


def add_archive_item(
    store: ArchiveStore,
    *,
    message_id: int,
    title: str,
    primary_interest: str,
    secondary_interests: list[str],
    topic: str,
    tags: list[str],
    classification_reason: str = "classified by test",
    confidence: float = 0.8,
    needs_review: bool = False,
    key_points: list[str] | None = None,
    insight_seed: str = "connect later",
    raw_text: str | None = None,
) -> str:
    capture_id = store.add_capture(
        capture_key=f"chat:{message_id}",
        chat_id="chat",
        message_id=message_id,
        chat_type="private",
        chat_title="me",
        sender_user_id="42",
        sender_name="User",
        message_date=None,
        text=title,
        caption="",
        content_kind="text",
        raw_message={"message_id": message_id},
    )
    store.upsert_archive_item(
        capture_id,
        {
            "title": title,
            "core_summary": f"{title} summary",
            "key_points": [f"{title} point"] if key_points is None else key_points,
            "raw_extracted_text": title if raw_text is None else raw_text,
            "source_language": "en",
            "primary_interest": primary_interest,
            "secondary_interests": secondary_interests,
            "topic": topic,
            "tags": tags,
            "classification_reason": classification_reason,
            "revisit_priority": "medium",
            "insight_seed": insight_seed,
            "confidence": confidence,
            "needs_review": needs_review,
        },
    )
    return capture_id


def make_cli_settings(
    tmp_path,
    *,
    token: str = "",
    chat_ids: tuple[str, ...] = (),
    codex_enabled: bool = False,
) -> Settings:
    return Settings(
        root=tmp_path,
        telegram_bot_token=token,
        telegram_allowed_chat_ids=chat_ids,
        telegram_admin_user_ids=("42",),
        telegram_allow_all_chats=False,
        state_dir=tmp_path / ".local" / "state",
        log_dir=tmp_path / ".local" / "logs",
        media_dir=tmp_path / ".local" / "captures",
        codex_enabled=codex_enabled,
        codex_bin="python3",
        codex_model="",
        codex_sandbox="read-only",
        codex_ephemeral=True,
        codex_timeout_sec=30,
        processor_batch_size=10,
        tesseract_bin="tesseract",
    )
