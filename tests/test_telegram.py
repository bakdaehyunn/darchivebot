from __future__ import annotations

from pathlib import Path
from typing import Any

from darchivebot.storage import ArchiveStore
from darchivebot.telegram import TelegramCaptureBot, extract_attachments, parse_command

from conftest import make_settings


class FakeTelegramApi:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def get_file(self, file_id: str) -> dict[str, Any]:
        return {"file_path": f"photos/{file_id}.jpg"}

    def download_file(self, file_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"image")

    def send_message(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


def test_parse_command_handles_bot_suffix():
    assert parse_command("/chatid@darchivebot hello") == "/chatid"
    assert parse_command("hello") == ""


def test_extract_photo_attachment_uses_largest_photo():
    message = {
        "photo": [
            {"file_id": "small", "file_unique_id": "s", "file_size": 10},
            {"file_id": "large", "file_unique_id": "l", "file_size": 20},
        ]
    }
    attachments = extract_attachments(message)
    assert attachments[0]["file_id"] == "large"


def test_capture_photo_downloads_media_and_records_file(tmp_path):
    settings = make_settings(tmp_path)
    store = ArchiveStore(settings.state_dir)
    api = FakeTelegramApi()
    bot = TelegramCaptureBot(settings, store, api=api)  # type: ignore[arg-type]

    capture_id = bot.handle_update(
        {
            "update_id": 1,
            "message": {
                "message_id": 7,
                "date": 1_700_000_000,
                "chat": {"id": 123, "type": "private", "first_name": "Me"},
                "from": {"id": 42, "first_name": "Me"},
                "caption": "캡처 내용",
                "photo": [{"file_id": "photo1", "file_unique_id": "p1", "file_size": 100}],
            },
        }
    )

    assert capture_id is not None
    files = store.files_for_capture(capture_id)
    assert len(files) == 1
    assert files[0]["download_status"] == "downloaded"
    assert Path(files[0]["local_path"]).exists()
