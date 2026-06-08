from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import httpx


TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass
class TelegramSendResult:
    ok: bool
    sent_count: int
    error: str | None = None


def format_telegram_text(text: str) -> str:
    content = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    content = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", content)
    content = content.replace("```", "")
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", content)
    content = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
    content = re.sub(r"__(.+?)__", r"\1", content)
    content = re.sub(r"`([^`]+)`", r"\1", content)

    cleaned_lines: list[str] = []
    for line in content.split("\n"):
        value = line.rstrip()
        value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value)
        value = re.sub(r"^\s*[*+-]\s+", "- ", value)
        value = re.sub(r"^\s*>\s?", "", value)
        cleaned_lines.append(value)

    normalized = "\n".join(cleaned_lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized or (text or "")


def split_telegram_text(text: str, *, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    content = text or ""
    if not content:
        return [""]
    chunks: list[str] = []
    remaining = content
    while remaining:
        chunk = remaining[:limit]
        chunks.append(chunk)
        remaining = remaining[limit:]
    return chunks


class TelegramBotClient:
    def __init__(
        self,
        *,
        token: str,
        http_client: httpx.Client | None = None,
        base_url: str = "https://api.telegram.org",
        request_timeout_seconds: float = 30,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._owns_http_client = http_client is None
        self.http_client = http_client or httpx.Client(timeout=request_timeout_seconds)
        self.request_timeout_seconds = request_timeout_seconds

    def __enter__(self) -> "TelegramBotClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http_client:
            self.http_client.close()

    def send_message(self, *, chat_id: str, text: str) -> TelegramSendResult:
        sent_count = 0
        for chunk in split_telegram_text(format_telegram_text(text)):
            response = self.http_client.post(
                self._method_url("sendMessage"),
                json={
                    "chat_id": str(chat_id),
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
            )
            try:
                payload = response.json()
            except ValueError:
                payload = {"ok": False, "description": response.text}
            if response.status_code >= 400 or not payload.get("ok", False):
                return TelegramSendResult(
                    ok=False,
                    sent_count=sent_count,
                    error=str(payload.get("description") or response.text or response.status_code),
                )
            sent_count += 1
        return TelegramSendResult(ok=True, sent_count=sent_count)

    def get_updates(self, *, offset: int | None = None, timeout_seconds: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout_seconds, "limit": limit}
        if offset is not None:
            params["offset"] = offset
        response = self.http_client.get(self._method_url("getUpdates"), params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok", False):
            raise RuntimeError(str(payload.get("description") or "Telegram getUpdates failed"))
        result = payload.get("result") or []
        return [item for item in result if isinstance(item, dict)]

    def _method_url(self, method: str) -> str:
        return f"{self.base_url}/bot{self.token}/{method}"
