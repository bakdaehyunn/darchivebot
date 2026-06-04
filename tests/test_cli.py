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
    assert "would send test message to 123" in capsys.readouterr().out


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
    assert "darchive_chat_id=-100123" in output
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
