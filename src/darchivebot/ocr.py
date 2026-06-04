from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class OcrAdapter:
    def extract_text(self, path: Path) -> str:
        raise NotImplementedError


class NoopOcrAdapter(OcrAdapter):
    def extract_text(self, path: Path) -> str:
        return ""


class TesseractOcrAdapter(OcrAdapter):
    def __init__(self, tesseract_bin: str = "tesseract") -> None:
        self.tesseract_bin = tesseract_bin

    def available(self) -> bool:
        return shutil.which(self.tesseract_bin) is not None

    def extract_text(self, path: Path) -> str:
        if not self.available():
            return ""
        proc = subprocess.run(
            [self.tesseract_bin, str(path), "stdout", "-l", "kor+eng"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()
