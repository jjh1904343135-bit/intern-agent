from __future__ import annotations

import json

import httpx

from app.services.telegram_client import TelegramBotClient, format_telegram_text, split_telegram_text
from app.services.telegram_offset_store import TelegramUpdateOffsetStore


def test_split_telegram_text_keeps_messages_under_limit() -> None:
    chunks = split_telegram_text("a" * 9000, limit=4096)

    assert len(chunks) == 3
    assert "".join(chunks) == "a" * 9000
    assert all(len(chunk) <= 4096 for chunk in chunks)


def test_format_telegram_text_removes_web_markdown_for_mobile_reading() -> None:
    raw = """### 🔍 美团开发岗求职分析

2. **岗位匹配 (Gap Analysis)**：对比你的简历与目标 JD。
* **如果你有现成的简历**：请直接粘贴简历内容。

```json
{"debug": true}
```
"""

    formatted = format_telegram_text(raw)

    assert "**" not in formatted
    assert "###" not in formatted
    assert "```" not in formatted
    assert "岗位匹配 (Gap Analysis)：对比你的简历与目标 JD。" in formatted
    assert "- 如果你有现成的简历：请直接粘贴简历内容。" in formatted
    assert "\n\n\n" not in formatted


def test_send_message_posts_each_split_chunk() -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(payloads)}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    bot = TelegramBotClient(token="token-123", http_client=http_client)

    result = bot.send_message(chat_id="42", text=("first segment\n" + "x" * 5000))

    assert result.ok is True
    assert result.sent_count == 2
    assert [payload["chat_id"] for payload in payloads] == ["42", "42"]
    assert "".join(payload["text"] for payload in payloads) == "first segment\n" + "x" * 5000


def test_send_message_formats_markdown_before_posting_to_telegram() -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(payloads)}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    bot = TelegramBotClient(token="token-123", http_client=http_client)

    result = bot.send_message(chat_id="42", text="**下一步行动建议：**\n* **上传简历**：我会先评分。")

    assert result.ok is True
    assert payloads[0]["text"] == "下一步行动建议：\n- 上传简历：我会先评分。"


def test_get_updates_passes_offset_and_timeout() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 11,
                        "message": {
                            "message_id": 7,
                            "date": 1770000000,
                            "chat": {"id": 42, "type": "private"},
                            "from": {"id": 99, "username": "alice"},
                            "text": "hello",
                        },
                    }
                ],
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    bot = TelegramBotClient(token="token-123", http_client=http_client)

    updates = bot.get_updates(offset=10, timeout_seconds=3)

    assert updates[0]["update_id"] == 11
    assert "offset=10" in seen_urls[0]
    assert "timeout=3" in seen_urls[0]


def test_bot_client_context_manager_closes_owned_http_client() -> None:
    bot = TelegramBotClient(token="token-123")
    owned_client = bot.http_client

    with bot as active:
        assert active is bot

    assert owned_client.is_closed is True


def test_bot_client_does_not_close_injected_http_client() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True, "result": []})))
    bot = TelegramBotClient(token="token-123", http_client=http_client)

    bot.close()

    assert http_client.is_closed is False
    http_client.close()


def test_update_offset_store_ignores_invalid_file_content(tmp_path) -> None:
    path = tmp_path / "offset.txt"
    path.write_text("broken", encoding="utf-8")
    store = TelegramUpdateOffsetStore(path)

    assert store.read() is None

    store.write(12)
    assert store.read() == 12
