from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from darchivebot.doctor import run_doctor
from darchivebot.storage import ArchiveStore

from conftest import make_settings


class FakeTelegramApi:
    def __init__(self, commands: list[dict[str, str]] | None = None) -> None:
        self.commands = [{"command": "chatid", "description": "현재 채팅방 ID 확인"}] if commands is None else commands

    def get_me(self) -> dict[str, object]:
        return {"ok": True, "result": {"username": "darchivebot"}}

    def get_my_commands(self, scope: dict[str, str] | None = None) -> list[dict[str, str]]:
        if scope is not None:
            return [
                {"command": "chatid", "description": "현재 채팅방 ID 확인"},
                {"command": "set_chat_room", "description": "현재 채팅방을 다카이브봇 사용 방으로 등록"},
            ]
        return self.commands


def test_doctor_reports_online_telegram_and_registered_room(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.state_dir.mkdir(parents=True)
    (settings.state_dir / "telegram_rooms.json").write_text(
        json.dumps({"darchive_chat_id": "-100123"}),
        encoding="utf-8",
    )

    code, text = run_doctor(settings, ArchiveStore(settings.state_dir), online=True, telegram_api=FakeTelegramApi())

    assert code == 0
    assert "[OK] darchive_chat_id is registered: ***0123" in text
    assert "[OK] Telegram getMe: @darchivebot" in text
    assert "[OK] Telegram registered chat command menu is synced" in text


def test_doctor_warns_when_commands_are_out_of_sync(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    api = FakeTelegramApi(commands=[])

    code, text = run_doctor(settings, ArchiveStore(settings.state_dir), online=True, telegram_api=api)

    assert code == 0
    assert "Telegram default command menu is out of sync" in text
    assert "darchive telegram-commands sync" in text


def test_doctor_warns_about_group_privacy_and_409_conflicts(tmp_path: Path) -> None:
    settings = replace(make_settings(tmp_path), telegram_allowed_chat_ids=("-100123",), telegram_allow_all_chats=False)
    settings.log_dir.mkdir(parents=True)
    (settings.log_dir / "telegram.log").write_text("urllib.error.HTTPError: HTTP Error 409: Conflict\n", encoding="utf-8")

    code, text = run_doctor(settings, ArchiveStore(settings.state_dir), online=False)

    assert code == 0
    assert "Group chat detected" in text
    assert "Recent Telegram 409 polling conflict" in text
    assert "Normal operation" in text
    assert "when none exist, it exits without Codex work" in text
