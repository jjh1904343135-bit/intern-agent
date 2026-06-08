from __future__ import annotations

from pathlib import Path


DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "evaluation" / "interview-agent-story.md"


def render_interview_depth_report() -> str:
    return """# 模拟面试 Agent 主故事

## 核心定位
模拟面试助手不是普通聊天机器人，而是一个围绕“岗位 × 简历”运行的有状态 Agent。

## 状态机
`job_profile -> candidate_profile -> question_plan -> asked_questions -> answer_signals -> evaluation_state -> followup_strategy -> summary_report`

## 面试官可追问的证据
- 为什么问这题：来自岗位 JD 的职责、技能要求和简历中的项目交集。
- 为什么追问：来自回答信号，如完整度、深度、具体性、ownership 和 red flags。
- 为什么调难度：回答越具体、越能解释取舍和指标，难度越高；回答过短或泛泛而谈会先澄清。
- 为什么给这个结论：报告中的 score_dimensions、evidence_chain、risk_points 和 improvement_suggestions。

## 当前边界
- 不接入八股 RAG 主链路，避免模拟面试变成知识库问答。
- 不暴露内部推理链，只展示可解释证据摘要。
- 不做语音、代码执行或自动外部工具调用。
"""


def write_interview_depth_report(path: Path = DEFAULT_REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_interview_depth_report(), encoding="utf-8")


def main() -> int:
    write_interview_depth_report()
    print(render_interview_depth_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
