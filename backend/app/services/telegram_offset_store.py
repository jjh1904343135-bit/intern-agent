from __future__ import annotations

from pathlib import Path


class TelegramUpdateOffsetStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> int | None:
        try:
            text = self.path.read_text(encoding="utf-8").strip()
            return int(text) if text else None
        except FileNotFoundError:
            return None
        except ValueError:
            return None

    def write(self, offset: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(offset), encoding="utf-8")
