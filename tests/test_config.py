from __future__ import annotations

import os

from darchivebot.config import resolve_executable


def test_resolve_executable_uses_extra_dirs_when_path_is_minimal(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "codex"
    executable.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    assert resolve_executable("codex", extra_dirs=(bin_dir,)) == str(executable)


def test_resolve_executable_preserves_explicit_paths(tmp_path):
    executable = tmp_path / "codex"
    executable.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    assert resolve_executable(str(executable)) == str(executable)


def test_resolve_executable_falls_back_to_original_value(monkeypatch):
    monkeypatch.setenv("PATH", os.devnull)

    assert resolve_executable("not-a-real-darchive-command", extra_dirs=()) == "not-a-real-darchive-command"
