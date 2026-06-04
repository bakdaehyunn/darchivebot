from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from darchivebot.config import Settings
from darchivebot.json_utils import dumps
from darchivebot.storage import ArchiveStore


DEFAULT_BOT_COMMANDS = [
    {"command": "chatid", "description": "현재 채팅방 ID 확인"},
]
REGISTERED_CHAT_BOT_COMMANDS = [
    *DEFAULT_BOT_COMMANDS,
    {"command": "set_chat_room", "description": "현재 채팅방을 다카이브봇 사용 방으로 등록"},
]
REGISTER_CHAT_ROOM_COMMAND = "/set_chat_room"


@dataclass(frozen=True)
class TelegramChatCandidate:
    chat_id: str
    title: str
    chat_type: str


@dataclass(frozen=True)
class TelegramRoomState:
    darchive_chat_id: str = ""
    darchive_chat_title: str = ""
    darchive_chat_type: str = ""
    registered_by_user_id: str = ""
    registered_at: str = ""
    unreadable_error: str = ""


class TelegramApiClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def get_me(self) -> dict[str, Any]:
        return self._api("getMe")

    def get_updates(
        self,
        offset: int | None = None,
        timeout: int | None = None,
        limit: int | None = 100,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {}
        if offset is not None:
            params["offset"] = offset
        if timeout is not None:
            params["timeout"] = timeout
        if limit is not None:
            params["limit"] = limit
        request_timeout = (timeout + 5) if timeout is not None else 15
        return self._api("getUpdates", params, request_timeout=request_timeout)

    def get_file(self, file_id: str) -> dict[str, Any]:
        payload = self._api("getFile", {"file_id": file_id})
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    def send_message(self, chat_id: str, text: str) -> None:
        self._api(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"},
            method="POST",
        )

    def get_my_commands(self, scope: dict[str, str] | None = None) -> list[dict[str, str]]:
        params: dict[str, str] = {}
        if scope is not None:
            params["scope"] = dumps(scope)
        payload = self._api("getMyCommands", params)
        result = payload.get("result")
        if not isinstance(result, list):
            return []
        commands: list[dict[str, str]] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            commands.append(
                {
                    "command": str(item.get("command") or ""),
                    "description": str(item.get("description") or ""),
                }
            )
        return commands

    def set_my_commands(self, commands: list[dict[str, str]], scope: dict[str, str] | None = None) -> None:
        params = {"commands": dumps(commands)}
        if scope is not None:
            params["scope"] = dumps(scope)
        self._api("setMyCommands", params, method="POST")

    def download_file(self, file_path: str, destination: Path) -> None:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        req = Request(url, method="GET")
        with urlopen(req, timeout=30) as resp:
            destination.write_bytes(resp.read())

    def _api(
        self,
        method_name: str,
        params: dict[str, str | int] | None = None,
        method: str = "GET",
        request_timeout: int = 15,
    ) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        params = params or {}
        url = f"https://api.telegram.org/bot{self.token}/{method_name}"
        data = None
        if method == "GET":
            if params:
                url = f"{url}?{urlencode(params)}"
        else:
            data = urlencode(params).encode("utf-8")
        req = Request(url, data=data, method=method)
        with urlopen(req, timeout=request_timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, dict) or not payload.get("ok"):
            raise RuntimeError(f"Telegram API failed: {payload}")
        return payload


class TelegramCaptureBot:
    def __init__(
        self,
        settings: Settings,
        store: ArchiveStore,
        api: TelegramApiClient | None = None,
    ) -> None:
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        self.settings = settings
        self.store = store
        self.api = api or TelegramApiClient(settings.telegram_bot_token)
        self.logger = build_logger(settings)

    def run_polling(self, poll_interval_sec: float = 1.0) -> None:
        offset: int | None = None
        while True:
            try:
                updates = self.get_updates(offset=offset, timeout=30)
                for update in updates:
                    offset = max(offset or 0, int(update.get("update_id", 0)) + 1)
                    self.handle_update(update)
            except Exception:
                self.logger.exception("telegram polling failed")
                time.sleep(max(1.0, poll_interval_sec))
            time.sleep(poll_interval_sec)

    def get_updates(self, offset: int | None, timeout: int = 30) -> list[dict[str, Any]]:
        payload = self.api.get_updates(offset=offset, timeout=timeout, limit=None)
        result = payload.get("result")
        return result if isinstance(result, list) else []

    def handle_update(self, update: dict[str, Any]) -> str | None:
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat")
        if not isinstance(chat, dict):
            return None
        chat_id = str(chat.get("id") or "")
        text = str(message.get("text") or "")
        command = parse_command(text)
        if command in {"/chatid", REGISTER_CHAT_ROOM_COMMAND}:
            self.handle_admin_command(command, chat_id, chat, message, text)
            return None
        if command:
            return None
        if not self.is_allowed(chat_id):
            return None
        return self.capture_message(message)

    def capture_message(self, message: dict[str, Any]) -> str:
        chat = object_value(message.get("chat"))
        user = object_value(message.get("from"))
        chat_id = str(chat.get("id") or "")
        message_id = int(message.get("message_id") or 0)
        text = str(message.get("text") or "")
        caption = str(message.get("caption") or "")
        attachments = extract_attachments(message)
        content_kind = content_kind_for_message(text, caption, attachments)
        capture_id = self.store.add_capture(
            capture_key=f"{chat_id}:{message_id}",
            chat_id=chat_id,
            message_id=message_id,
            chat_type=str(chat.get("type") or ""),
            chat_title=chat_display_name(chat),
            sender_user_id=str(user.get("id") or ""),
            sender_name=user_display_name(user),
            message_date=int(message["date"]) if isinstance(message.get("date"), int) else None,
            text=text,
            caption=caption,
            content_kind=content_kind,
            raw_message=message,
        )
        for attachment in attachments:
            local_path, status = self.download_attachment(capture_id, message, attachment)
            self.store.add_file(
                capture_id=capture_id,
                telegram_file_id=attachment["file_id"],
                telegram_file_unique_id=attachment.get("file_unique_id", ""),
                file_kind=attachment["kind"],
                mime_type=attachment.get("mime_type", ""),
                file_name=attachment.get("file_name", ""),
                file_size=attachment.get("file_size"),
                local_path=str(local_path) if local_path else "",
                download_status=status,
            )
        return capture_id

    def download_attachment(
        self,
        capture_id: str,
        message: dict[str, Any],
        attachment: dict[str, Any],
    ) -> tuple[Path | None, str]:
        try:
            file_payload = self.api.get_file(attachment["file_id"])
            file_path = str(file_payload.get("file_path") or "")
            if not file_path:
                return None, "missing_file_path"
            destination = self.local_media_path(capture_id, message, attachment, file_path)
            self.api.download_file(file_path, destination)
            return destination, "downloaded"
        except Exception:
            self.logger.exception("failed to download Telegram file capture_id=%s", capture_id)
            return None, "failed"

    def local_media_path(
        self,
        capture_id: str,
        message: dict[str, Any],
        attachment: dict[str, Any],
        telegram_file_path: str,
    ) -> Path:
        timestamp = datetime.fromtimestamp(int(message.get("date") or time.time()))
        folder = self.settings.media_dir / timestamp.strftime("%Y") / timestamp.strftime("%m") / timestamp.strftime("%d")
        raw_name = attachment.get("file_name") or Path(telegram_file_path).name or f"{capture_id}.bin"
        file_name = safe_file_name(raw_name)
        return folder / f"{capture_id}-{attachment['kind']}-{file_name}"

    def handle_admin_command(
        self,
        command: str,
        chat_id: str,
        chat: dict[str, Any],
        message: dict[str, Any],
        text: str,
    ) -> None:
        if not self.is_admin_message(message):
            return
        if command == "/chatid":
            self.api.send_message(chat_id, f"chat_id: {chat_id}\ntype: {chat.get('type') or ''}\ntitle: {chat_display_name(chat)}")
            return
        if command == REGISTER_CHAT_ROOM_COMMAND:
            if not self.can_overwrite_registered_room(chat_id, chat, text):
                return
            self.save_registered_room(chat_id, chat, message)
            self.api.send_message(chat_id, f"다카이브봇 사용 방으로 등록했습니다.\nchat_id: {chat_id}")
            self.sync_registered_chat_commands(chat_id)

    def can_overwrite_registered_room(self, chat_id: str, chat: dict[str, Any], text: str) -> bool:
        state = read_room_state(self.settings)
        if not state.darchive_chat_id or state.darchive_chat_id == chat_id:
            return True
        if command_argument(text) == "confirm":
            return True
        self.api.send_message(
            chat_id,
            (
                "이미 다른 방이 다카이브봇 사용 방으로 등록되어 있습니다.\n"
                f"기존: {state.darchive_chat_id} / {state.darchive_chat_title or '(empty)'}\n"
                f"새 방: {chat_id} / {chat_display_name(chat) or '(empty)'}\n"
                f"정말 바꾸려면 {REGISTER_CHAT_ROOM_COMMAND} confirm 을 보내주세요."
            ),
        )
        return False

    def sync_registered_chat_commands(self, chat_id: str) -> None:
        try:
            self.api.set_my_commands(REGISTERED_CHAT_BOT_COMMANDS, scope=chat_command_scope(chat_id))
        except Exception:
            self.logger.exception("failed to sync registered chat Telegram commands")

    def save_registered_room(self, chat_id: str, chat: dict[str, Any], message: dict[str, Any]) -> None:
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.state_dir / "telegram_rooms.json"
        user = object_value(message.get("from"))
        data = {
            "darchive_chat_id": chat_id,
            "darchive_chat_title": chat_display_name(chat),
            "darchive_chat_type": str(chat.get("type") or ""),
            "registered_by_user_id": str(user.get("id") or ""),
            "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def is_admin_message(self, message: dict[str, Any]) -> bool:
        allowed = self.settings.telegram_admin_user_ids
        if not allowed:
            return False
        user = message.get("from")
        if not isinstance(user, dict):
            return False
        return str(user.get("id") or "") in allowed

    def is_allowed(self, chat_id: str) -> bool:
        allowed = allowed_chat_ids(self.settings)
        if allowed:
            return chat_id in allowed
        return self.settings.telegram_allow_all_chats


def extract_attachments(message: dict[str, Any]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        candidates = [item for item in photos if isinstance(item, dict)]
        if candidates:
            selected = max(candidates, key=lambda item: int(item.get("file_size") or 0))
            attachments.append(
                {
                    "kind": "photo",
                    "file_id": str(selected.get("file_id") or ""),
                    "file_unique_id": str(selected.get("file_unique_id") or ""),
                    "file_size": int(selected.get("file_size") or 0),
                    "mime_type": "image/jpeg",
                    "file_name": "photo.jpg",
                }
            )
    document = message.get("document")
    if isinstance(document, dict):
        attachments.append(
            {
                "kind": "document",
                "file_id": str(document.get("file_id") or ""),
                "file_unique_id": str(document.get("file_unique_id") or ""),
                "file_size": int(document.get("file_size") or 0),
                "mime_type": str(document.get("mime_type") or ""),
                "file_name": str(document.get("file_name") or "document"),
            }
        )
    return [item for item in attachments if item["file_id"]]


def content_kind_for_message(text: str, caption: str, attachments: list[dict[str, Any]]) -> str:
    kinds = {item["kind"] for item in attachments}
    if "photo" in kinds:
        return "screenshot" if caption_or_text_mentions_screenshot(text, caption) else "photo"
    if "document" in kinds:
        return "document"
    return "text"


def caption_or_text_mentions_screenshot(text: str, caption: str) -> bool:
    haystack = f"{text} {caption}".lower()
    return any(token in haystack for token in ("screenshot", "screen shot", "capture", "캡처", "스크린샷"))


def parse_command(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return ""
    return stripped.split(maxsplit=1)[0].split("@", 1)[0]


def command_argument(text: str) -> str:
    stripped = text.strip()
    parts = stripped.split(maxsplit=1)
    return parts[1].strip().lower() if len(parts) > 1 else ""


def read_room_state(settings: Settings) -> TelegramRoomState:
    path = settings.state_dir / "telegram_rooms.json"
    if not path.exists():
        return TelegramRoomState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return TelegramRoomState(unreadable_error=str(exc))
    if not isinstance(payload, dict):
        return TelegramRoomState(unreadable_error="telegram room state is not a JSON object")
    return TelegramRoomState(
        darchive_chat_id=str(payload.get("darchive_chat_id") or "").strip(),
        darchive_chat_title=str(payload.get("darchive_chat_title") or "").strip(),
        darchive_chat_type=str(payload.get("darchive_chat_type") or "").strip(),
        registered_by_user_id=str(payload.get("registered_by_user_id") or "").strip(),
        registered_at=str(payload.get("registered_at") or "").strip(),
    )


def read_registered_chat_id(settings: Settings) -> str:
    return read_room_state(settings).darchive_chat_id


def allowed_chat_ids(settings: Settings) -> set[str]:
    allowed = set(settings.telegram_allowed_chat_ids)
    registered = read_registered_chat_id(settings)
    if registered:
        allowed.add(registered)
    return allowed


def chat_command_scope(chat_id: str) -> dict[str, str]:
    return {"type": "chat", "chat_id": chat_id}


def command_menu_is_synced(commands: list[dict[str, str]], expected: list[dict[str, str]]) -> bool:
    normalized = [
        {
            "command": str(item.get("command") or ""),
            "description": str(item.get("description") or ""),
        }
        for item in commands
    ]
    return normalized == expected


def format_rooms_report(settings: Settings) -> tuple[int, str]:
    state = read_room_state(settings)
    if state.unreadable_error:
        return 1, f"[FAIL] telegram room state is unreadable: {state.unreadable_error}"
    lines: list[str] = []
    if state.darchive_chat_id:
        lines.extend(
            [
                f"darchive_chat_id={state.darchive_chat_id}",
                f"title={state.darchive_chat_title or '(empty)'}",
                f"type={state.darchive_chat_type or '(empty)'}",
                f"registered_by_user_id={state.registered_by_user_id or '(empty)'}",
                f"registered_at={state.registered_at or '(empty)'}",
                f"allowed={'yes' if state.darchive_chat_id in allowed_chat_ids(settings) else 'no'}",
            ]
        )
    else:
        lines.append(f"[WARN] darchive_chat_id is not registered; send {REGISTER_CHAT_ROOM_COMMAND} in the Telegram chat")
    if settings.telegram_allowed_chat_ids:
        lines.append(f"env_allowed_chat_ids={','.join(settings.telegram_allowed_chat_ids)}")
    elif settings.telegram_allow_all_chats:
        lines.append("[WARN] DARCHIVE_ALLOW_ALL_CHATS=true; every chat can use the bot")
    else:
        lines.append("env_allowed_chat_ids=(empty)")
    return 0, "\n".join(lines)


def discover_chat_candidates(payload: dict[str, Any]) -> list[TelegramChatCandidate]:
    result = payload.get("result", [])
    if not isinstance(result, list):
        return []
    candidates: list[TelegramChatCandidate] = []
    seen: set[str] = set()
    for update in result:
        if not isinstance(update, dict):
            continue
        for key in ("message", "edited_message", "channel_post", "edited_channel_post", "my_chat_member", "chat_member"):
            event = update.get(key)
            if not isinstance(event, dict):
                continue
            chat = event.get("chat")
            if not isinstance(chat, dict):
                continue
            raw_chat_id = chat.get("id")
            if raw_chat_id is None:
                continue
            chat_id = str(raw_chat_id)
            if chat_id in seen:
                continue
            seen.add(chat_id)
            candidates.append(
                TelegramChatCandidate(
                    chat_id=chat_id,
                    title=chat_display_name(chat),
                    chat_type=str(chat.get("type") or ""),
                )
            )
    return candidates


def object_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def chat_display_name(chat: dict[str, Any]) -> str:
    return str(chat.get("title") or chat.get("username") or chat.get("first_name") or chat.get("type") or chat.get("id") or "")


def user_display_name(user: dict[str, Any]) -> str:
    parts = [str(user.get("first_name") or ""), str(user.get("last_name") or "")]
    name = " ".join(part for part in parts if part).strip()
    return name or str(user.get("username") or user.get("id") or "")


def safe_file_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in value)
    return cleaned[:180] or "file"


def build_logger(settings: Settings) -> logging.Logger:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("darchivebot.telegram")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(settings.log_dir / "telegram.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger
