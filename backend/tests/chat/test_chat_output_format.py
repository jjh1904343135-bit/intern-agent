from __future__ import annotations

from app.services.chat_output_format import format_assistant_plain_text


def test_format_assistant_plain_text_removes_markdown_without_losing_content() -> None:
    raw = """
### 美团开发岗分析

**已识别条件：**
- 公司：美团
- 岗位：Java 后端

```json
{"debug": true}
```

1. **匹配原因**：你的项目里有 FastAPI 和 Redis。
"""

    formatted = format_assistant_plain_text(raw)

    assert "###" not in formatted
    assert "**" not in formatted
    assert "```" not in formatted
    assert "- 公司" not in formatted
    assert "美团开发岗分析" in formatted
    assert "公司：美团" in formatted
    assert "岗位：Java 后端" in formatted
    assert "匹配原因：你的项目里有 FastAPI 和 Redis。" in formatted
