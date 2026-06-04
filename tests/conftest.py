from __future__ import annotations

from pathlib import Path

from darchivebot.config import Settings


def make_settings(root: Path, *, codex_enabled: bool = True) -> Settings:
    return Settings(
        root=root,
        telegram_bot_token="token",
        telegram_allowed_chat_ids=(),
        telegram_admin_user_ids=("42",),
        telegram_allow_all_chats=True,
        state_dir=root / ".local" / "state",
        log_dir=root / ".local" / "logs",
        media_dir=root / ".local" / "captures",
        codex_enabled=codex_enabled,
        codex_bin="codex",
        codex_model="",
        codex_sandbox="read-only",
        codex_ephemeral=True,
        codex_timeout_sec=30,
        processor_batch_size=10,
        tesseract_bin="tesseract",
    )
