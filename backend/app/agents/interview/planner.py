from __future__ import annotations

from app.agents.interview.models import CandidateProfile, JobProfile, PlannedQuestion


def build_question_plan(*, job_profile: JobProfile, candidate_profile: CandidateProfile, round_type: str = "mixed", difficulty: int = 2) -> list[PlannedQuestion]:
    matched = candidate_profile.matched_skills or candidate_profile.skills[:3] or job_profile.must_have_skills[:3]
    primary_skill = matched[0] if matched else (job_profile.must_have_skills[0] if job_profile.must_have_skills else "岗位核心能力")
    project_name = _primary_project_name(candidate_profile)
    matched_text = "、".join(matched[:4]) or primary_skill
    missing_text = "、".join(candidate_profile.missing_skills[:3]) or "岗位要求中的关键取舍"
    responsibility_text = "；".join(job_profile.responsibilities[:2])
    focus_text = "、".join(job_profile.interview_focus[:4])

    return [
        PlannedQuestion(
            id="q-1",
            category="experience",
            skill_tag=primary_skill,
            prompt=(
                f"请结合你简历中的 {project_name} 项目，说明你如何使用 {matched_text} 支撑 "
                f"{job_profile.company or '目标公司'} 的 {job_profile.title} 岗位要求。"
                f"岗位职责片段：{responsibility_text}。本轮关注：{focus_text}。"
                "请按背景、你的动作、结果和复盘来回答。"
            ),
            ideal_signals=["项目背景", "本人动作", "量化结果", primary_skill],
            followup_axes=["clarify", "drill_down", "challenge"],
            difficulty=difficulty,
        ),
        PlannedQuestion(
            id="q-2",
            category="technical",
            skill_tag=primary_skill,
            prompt=f"围绕 {primary_skill} 做一次技术下钻：你会如何设计关键流程、处理失败场景，并验证效果？",
            ideal_signals=["架构拆分", "失败处理", "指标验证", primary_skill],
            followup_axes=["drill_down", "challenge", "transfer"],
            difficulty=min(difficulty + 1, 5),
        ),
        PlannedQuestion(
            id="q-3",
            category="system_design",
            skill_tag=missing_text,
            prompt=f"如果这个岗位要求你补强 {missing_text}，你会如何在 2 周内学习、验证并落到项目里？",
            ideal_signals=["计划", "验证", "交付", "风险"],
            followup_axes=["challenge", "transfer"],
            difficulty=min(difficulty + 1, 5),
        ),
        PlannedQuestion(
            id="q-4",
            category="behavioral",
            skill_tag="沟通协作",
            prompt="讲一次你和产品、算法、后端或业务同学协作推进复杂问题的经历，你如何对齐目标和取舍？",
            ideal_signals=["冲突", "沟通", "取舍", "结果"],
            followup_axes=["clarify", "transfer"],
            difficulty=difficulty,
        ),
    ]


def _primary_project_name(candidate_profile: CandidateProfile) -> str:
    for project in candidate_profile.projects:
        name = str(project.get("name") or "").strip()
        if name:
            return name
    return "最相关"
