from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def file_lock(path: Path, stale_after_seconds: int = 30 * 60) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, f"{os.getpid()}\n{int(time.time())}\n".encode("ascii"))
        yield True
    except FileExistsError:
        if clear_stale_lock(path, stale_after_seconds):
            with file_lock(path, stale_after_seconds=stale_after_seconds) as acquired:
                yield acquired
        else:
            yield False
    finally:
        if fd is not None:
            os.close(fd)
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def clear_stale_lock(path: Path, stale_after_seconds: int) -> bool:
    if stale_after_seconds < 1:
        return False
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return True
    if age < stale_after_seconds:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
