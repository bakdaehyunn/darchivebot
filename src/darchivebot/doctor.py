from __future__ import annotations

import shutil
import subprocess

from darchivebot.config import Settings, ensure_local_dirs
from darchivebot.storage import ArchiveStore
from darchivebot.telegram import (
    DEFAULT_BOT_COMMANDS,
    REGISTERED_CHAT_BOT_COMMANDS,
    TelegramApiClient,
    allowed_chat_ids,
    chat_command_scope,
    command_menu_is_synced,
    read_room_state,
)


def run_doctor(
    settings: Settings,
    store: ArchiveStore,
    *,
    online: bool = False,
    telegram_api: TelegramApiClient | None = None,
) -> tuple[int, str]:
    ensure_local_dirs(settings)
    store.init_db()
    lines: list[str] = []
    failures = 0

    lines.append(f"[OK] state_dir: {settings.state_dir}")
    lines.append(f"[OK] media_dir: {settings.media_dir}")
    lines.append(f"[OK] log_dir: {settings.log_dir}")
    lines.append(f"[OK] sqlite: {store.path}")

    if settings.telegram_bot_token:
        lines.append("[OK] TELEGRAM_BOT_TOKEN is set")
    else:
        lines.append("[WARN] TELEGRAM_BOT_TOKEN is missing")
        lines.append("[TODO] Add TELEGRAM_BOT_TOKEN to .env, then run: darchive doctor --online")

    if settings.telegram_allowed_chat_ids:
        lines.append(f"[OK] TELEGRAM_ALLOWED_CHAT_IDS is set: {','.join(settings.telegram_allowed_chat_ids)}")
    elif settings.telegram_allow_all_chats:
        lines.append("[WARN] DARCHIVE_ALLOW_ALL_CHATS=true; every chat can use the bot")
    else:
        lines.append("[OK] TELEGRAM_ALLOWED_CHAT_IDS is empty; only a registered room can use the bot")

    if settings.telegram_admin_user_ids:
        lines.append("[OK] TELEGRAM_ADMIN_USER_IDS is set")
    else:
        lines.append("[WARN] TELEGRAM_ADMIN_USER_IDS is empty; /chatid and /set_chat_room are disabled")

    room_failures, room_lines = describe_room_state(settings)
    failures += room_failures
    lines.extend(room_lines)

    codex_path = shutil.which(settings.codex_bin)
    if codex_path:
        lines.append(f"[OK] Codex CLI found: {codex_path}")
        try:
            proc = subprocess.run(
                [settings.codex_bin, "--version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            version = (proc.stdout or proc.stderr).strip().splitlines()
            if proc.returncode == 0 and version:
                lines.append(f"[OK] Codex CLI version: {version[0]}")
            else:
                lines.append("[WARN] Codex CLI exists but version check did not return cleanly")
        except Exception as exc:
            lines.append(f"[WARN] Codex CLI version check failed: {exc}")
    else:
        failures += 1
        lines.append(f"[FAIL] Codex CLI not found: {settings.codex_bin}")

    lines.append(f"[OK] Codex processor enabled: {str(settings.codex_enabled).lower()}")
    lines.append(f"[OK] Codex sandbox: {settings.codex_sandbox}")

    if online:
        telegram_failures, telegram_lines = describe_telegram_api_state(settings, telegram_api)
        failures += telegram_failures
        lines.extend(telegram_lines)
    elif settings.telegram_bot_token:
        lines.append("[WARN] Telegram API checks skipped; run: darchive doctor --online")

    return (1 if failures else 0), "\n".join(lines)


def describe_room_state(settings: Settings) -> tuple[int, list[str]]:
    state = read_room_state(settings)
    if state.unreadable_error:
        return 1, [f"[FAIL] telegram room state is unreadable: {state.unreadable_error}"]
    if state.darchive_chat_id:
        lines = [f"[OK] darchive_chat_id is registered: {state.darchive_chat_id}"]
        if state.darchive_chat_id in settings.telegram_allowed_chat_ids:
            lines.append("[OK] darchive_chat_id is also listed in TELEGRAM_ALLOWED_CHAT_IDS")
        else:
            lines.append("[OK] darchive_chat_id is allowed by runtime registration")
        return 0, lines
    if settings.telegram_allowed_chat_ids:
        return 0, ["[WARN] darchive_chat_id is not registered; env allow-list can still capture messages"]
    return 0, ["[WARN] darchive_chat_id is not registered; send /set_chat_room in the Telegram chat"]


def describe_telegram_api_state(
    settings: Settings,
    telegram_api: TelegramApiClient | None = None,
) -> tuple[int, list[str]]:
    if not settings.telegram_bot_token:
        return 0, ["[WARN] Telegram API checks skipped because TELEGRAM_BOT_TOKEN is missing"]

    failures = 0
    lines: list[str] = []
    api = telegram_api or TelegramApiClient(settings.telegram_bot_token)

    try:
        payload = api.get_me()
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        username = str(result.get("username") or "") if isinstance(result, dict) else ""
        lines.append(f"[OK] Telegram getMe: @{username}" if username else "[OK] Telegram getMe succeeded")
    except Exception as exc:
        failures += 1
        lines.append(f"[FAIL] Telegram getMe failed: {exc}")

    try:
        commands = api.get_my_commands()
        if command_menu_is_synced(commands, DEFAULT_BOT_COMMANDS):
            lines.append("[OK] Telegram default command menu is synced")
        else:
            lines.append(f"[WARN] Telegram default command menu is out of sync: {format_command_diff(commands, DEFAULT_BOT_COMMANDS)}")
            lines.append("[TODO] Run: darchive telegram-commands sync")
    except Exception as exc:
        lines.append(f"[WARN] Telegram default command menu check failed: {exc}")

    state = read_room_state(settings)
    if state.darchive_chat_id:
        try:
            commands = api.get_my_commands(scope=chat_command_scope(state.darchive_chat_id))
            if command_menu_is_synced(commands, REGISTERED_CHAT_BOT_COMMANDS):
                lines.append("[OK] Telegram registered chat command menu is synced")
            else:
                lines.append(
                    f"[WARN] Telegram registered chat command menu is out of sync: "
                    f"{format_command_diff(commands, REGISTERED_CHAT_BOT_COMMANDS)}"
                )
                lines.append("[TODO] Run: darchive telegram-commands sync")
        except Exception as exc:
            lines.append(f"[WARN] Telegram registered chat command menu check failed: {exc}")

    if not allowed_chat_ids(settings) and not settings.telegram_allow_all_chats:
        lines.append("[TODO] Add TELEGRAM_ALLOWED_CHAT_IDS or register a chat with /set_chat_room")

    return failures, lines


def format_command_diff(actual: list[dict[str, str]], expected: list[dict[str, str]]) -> str:
    expected_text = ", ".join(f"/{item['command']}" for item in expected)
    actual_text = ", ".join(f"/{item.get('command', '')}" for item in actual) or "(empty)"
    return f"expected={expected_text} actual={actual_text}"
