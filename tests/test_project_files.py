from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_covers_private_runtime_files():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert ".local/" in text
    assert "*.sqlite3" in text
    assert "*.log" in text


def test_launchd_scripts_reference_bot_and_processor():
    install = (ROOT / "scripts" / "install_launch_agent.sh").read_text(encoding="utf-8")
    assert "com.hennei.darchivebot.telegram" in install
    assert "com.hennei.darchivebot.processor" in install
    assert "<string>telegram</string>" in install
    assert "<string>process</string>" in install


def test_preflight_script_checks_private_runtime_files_and_secrets():
    preflight = (ROOT / "scripts" / "preflight_public.sh").read_text(encoding="utf-8")
    assert "git ls-files --error-unmatch .env" in preflight
    assert "*.sqlite3" in preflight
    assert "TELEGRAM_BOT_TOKEN" in preflight
