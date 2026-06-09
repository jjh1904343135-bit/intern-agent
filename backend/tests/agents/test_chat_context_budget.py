from __future__ import annotations

from app.agents.chat.context_budget import ChatContextBudget, estimate_tokens, maybe_compress_context


def test_context_budget_triggers_compression_at_half_context_window_and_keeps_recent_history() -> None:
    history = [
        {"role": "user", "content": f"第 {index} 轮问题：" + "很长的上下文" * 80}
        for index in range(16)
    ]
    file_memory_context = {"summary_text": "历史记忆：" + "求职偏好和项目事实" * 600}
    tool_context = {"knowledge_search": {"hits": [{"text": "知识片段" * 500}]}}

    result = maybe_compress_context(
        history=history,
        file_memory_context=file_memory_context,
        tool_context=tool_context,
        prompt="最终提示词" + "任务说明" * 400,
        budget=ChatContextBudget(context_window_tokens=1200, compression_ratio=0.5, reserved_output_tokens=100),
    )

    assert result["triggered"] is True
    assert result["threshold_ratio"] == 0.5
    assert result["threshold_tokens"] == 600
    assert result["before_tokens"] >= result["threshold_tokens"]
    assert result["after_tokens"] < result["before_tokens"]
    assert len(result["history"]) == 6
    assert result["history"][-1]["content"].startswith("第 15 轮问题")
    assert result["summary"]


def test_context_budget_skips_compression_below_half_context_window() -> None:
    history = [{"role": "user", "content": "你好"}]

    result = maybe_compress_context(
        history=history,
        file_memory_context={"summary_text": "短记忆"},
        tool_context={},
        prompt="短提示词",
        budget=ChatContextBudget(context_window_tokens=8192, compression_ratio=0.5, reserved_output_tokens=900),
    )

    assert result["triggered"] is False
    assert result["history"] == history
    assert result["before_tokens"] == result["after_tokens"]
    assert estimate_tokens("短提示词") > 0
