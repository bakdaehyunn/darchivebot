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
