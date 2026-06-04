from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = ROOT / ".env"


def load_env(path: Path | None = None) -> None:
    env_path = path or Path(os.environ.get("DARCHIVE_ENV_FILE", DEFAULT_ENV_FILE))
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = env_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = env_str(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


def env_tuple(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in env_str(name).split(",") if item.strip())


def resolve_path(raw: str, default: str, root: Path = ROOT) -> Path:
    value = raw or default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


@dataclass(frozen=True)
class Settings:
    root: Path
    telegram_bot_token: str
    telegram_allowed_chat_ids: tuple[str, ...]
    telegram_admin_user_ids: tuple[str, ...]
    telegram_allow_all_chats: bool
    state_dir: Path
    log_dir: Path
    media_dir: Path
    codex_enabled: bool
    codex_bin: str
    codex_model: str
    codex_sandbox: str
    codex_ephemeral: bool
    codex_timeout_sec: int
    processor_batch_size: int
    tesseract_bin: str


def get_settings(root: Path = ROOT) -> Settings:
    return Settings(
        root=root,
        telegram_bot_token=env_str("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_chat_ids=env_tuple("TELEGRAM_ALLOWED_CHAT_IDS"),
        telegram_admin_user_ids=env_tuple("TELEGRAM_ADMIN_USER_IDS"),
        telegram_allow_all_chats=env_bool("DARCHIVE_ALLOW_ALL_CHATS", False),
        state_dir=resolve_path(env_str("DARCHIVE_STATE_DIR"), ".local/state", root),
        log_dir=resolve_path(env_str("DARCHIVE_LOG_DIR"), ".local/logs", root),
        media_dir=resolve_path(env_str("DARCHIVE_MEDIA_DIR"), ".local/captures", root),
        codex_enabled=env_bool("DARCHIVE_CODEX_ENABLED", True),
        codex_bin=env_str("DARCHIVE_CODEX_BIN", "codex"),
        codex_model=env_str("DARCHIVE_CODEX_MODEL"),
        codex_sandbox=env_str("DARCHIVE_CODEX_SANDBOX", "read-only"),
        codex_ephemeral=env_bool("DARCHIVE_CODEX_EPHEMERAL", True),
        codex_timeout_sec=env_int("DARCHIVE_CODEX_TIMEOUT_SEC", 900),
        processor_batch_size=max(1, env_int("DARCHIVE_PROCESSOR_BATCH_SIZE", 10)),
        tesseract_bin=env_str("DARCHIVE_TESSERACT_BIN", "tesseract"),
    )


def ensure_local_dirs(settings: Settings) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
