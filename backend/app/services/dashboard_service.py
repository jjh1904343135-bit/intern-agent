from __future__ import annotations

from dataclasses import dataclass

from app.repositories.dashboard_repository import DashboardRepository


@dataclass
class DashboardServiceError(Exception):
    status_code: int
    code: int
    message: str


class DashboardService:
    ACTIVE_STATUSES = {
        "saved",
        "opened",
        "applied_manual",
        "waiting_feedback",
        "interviewing",
        "pending",
        "submitted",
        "viewed",
        "interview_invited",
        "offer_received",
    }

    def __init__(self, dashboard_repository: DashboardRepository):
        self.dashboard_repository = dashboard_repository

    def get_summary(self, *, user_id: str) -> dict:
        snapshot = self.dashboard_repository.get_dashboard_snapshot(user_id=user_id)
        latest_resume = snapshot["latest_resume"]
        applications = snapshot["applications"]
        interviews = snapshot["interviews"]
        chats = snapshot["chats"]

        status_breakdown: dict[str, int] = {}
        for item in applications:
            status_breakdown[item.status] = status_breakdown.get(item.status, 0) + 1

        active_count = sum(count for status, count in status_breakdown.items() if status in self.ACTIVE_STATUSES)
        latest_interview = interviews[0] if interviews else None
        latest_chat = chats[0] if chats else None

        next_actions = self._build_next_actions(
            latest_resume=latest_resume,
            applications=applications,
            interviews=interviews,
        )
        recommended_actions = self._build_recommended_actions(
            latest_resume=latest_resume,
            applications=applications,
            interviews=interviews,
        )

        return {
            "overview": {
                "resume_count": snapshot["resume_count"],
                "applications_total": len(applications),
                "active_applications": active_count,
                "interview_sessions": snapshot["interview_total"],
                "chat_sessions": snapshot["chat_total"],
            },
            "resume": self._serialize_resume(latest_resume),
            "applications": {
                "total": len(applications),
                "active_count": active_count,
                "status_breakdown": status_breakdown,
                "recent": [self._serialize_application(item) for item in applications[:3]],
            },
            "interview": {
                "total": snapshot["interview_total"],
                "latest": self._serialize_interview(latest_interview),
            },
            "chat": {
                "total": snapshot["chat_total"],
                "latest_preview": self._serialize_chat(latest_chat),
            },
            "next_actions": next_actions,
            "recommended_actions": recommended_actions,
        }

    @staticmethod
    def _serialize_resume(resume) -> dict | None:
        if resume is None:
            return None
        score_report = resume.score_report or None
        return {
            "resume_id": str(resume.id),
            "file_name": resume.file_name,
            "parse_status": resume.parse_status,
            "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
            "score": score_report,
        }

    @staticmethod
    def _serialize_application(application) -> dict:
        return {
            "application_id": str(application.id),
            "job_id": str(application.job_id),
            "status": application.status,
            "applied_at": application.applied_at.isoformat() if application.applied_at else None,
            "status_updated_at": application.status_updated_at.isoformat() if application.status_updated_at else None,
        }

    @staticmethod
    def _serialize_interview(interview) -> dict | None:
        if interview is None:
            return None
        report = interview.report or {}
        return {
            "session_id": str(interview.id),
            "mode": interview.mode,
            "started_at": interview.started_at.isoformat() if interview.started_at else None,
            "overall_score": report.get("overall_score"),
        }

    @staticmethod
    def _serialize_chat(chat) -> dict | None:
        if chat is None:
            return None
        messages = chat.messages or []
        assistant_messages = [item.get("content", "") for item in messages if item.get("role") == "assistant"]
        preview = assistant_messages[-1] if assistant_messages else ""
        return {
            "session_id": str(chat.id),
            "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
            "preview": preview[:120],
        }

    @classmethod
    def _build_next_actions(cls, *, latest_resume, applications: list, interviews: list) -> list[str]:
        actions: list[str] = []

        if latest_resume is None:
            actions.append("先上传一份简历，让系统生成评分、风险点和后续建议。")
            return actions

        score_report = latest_resume.score_report or {}
        if latest_resume.parse_status != "done":
            actions.append("等待简历解析完成，完成后再进入岗位匹配和投递。")
        elif score_report.get("next_actions"):
            actions.extend([str(item) for item in list(score_report["next_actions"])[:2]])

        if not applications:
            actions.append("去岗位页挑 1-3 个目标岗位，先建立第一批投递记录。")
        elif sum(1 for item in applications if item.status in cls.ACTIVE_STATUSES) > 0:
            actions.append("检查投递中心里仍在推进的申请，优先跟进状态最新的岗位。")

        if not interviews:
            actions.append("开始一次模拟面试，把回答质量和追问反馈也纳入训练闭环。")

        return actions[:3]

    @classmethod
    def _build_recommended_actions(cls, *, latest_resume, applications: list, interviews: list) -> list[dict[str, str | int]]:
        """Return structured next-step cards for the product dashboard."""
        actions: list[dict[str, str | int]] = []

        if latest_resume is None:
            return [
                {
                    "kind": "resume_upload",
                    "title": "上传简历",
                    "description": "先完成解析和评分，后续岗位推荐、投递建议和模拟面试才有上下文。",
                    "href": "/resume/upload",
                    "priority": 100,
                }
            ]

        if latest_resume.parse_status != "done":
            actions.append(
                {
                    "kind": "resume_processing",
                    "title": "查看简历解析进度",
                    "description": "简历还在处理中，完成后再进入岗位匹配和投递。",
                    "href": f"/resume/{latest_resume.id}/status",
                    "priority": 95,
                }
            )
            return actions

        if not applications:
            actions.append(
                {
                    "kind": "job_search",
                    "title": "搜索目标岗位",
                    "description": "简历已解析，下一步保存 1-3 个真实岗位进入投递清单。",
                    "href": "/jobs",
                    "priority": 90,
                }
            )
        else:
            active = [item for item in applications if item.status in cls.ACTIVE_STATUSES]
            saved_or_opened = [item for item in applications if item.status in {"saved", "opened"}]
            applied = [item for item in applications if item.status in {"applied_manual", "submitted", "waiting_feedback"}]
            if saved_or_opened:
                actions.append(
                    {
                        "kind": "application_followup",
                        "title": "完成原站投递",
                        "description": "有岗位已保存或已打开，建议去原站提交并回到投递中心记录状态。",
                        "href": "/applications",
                        "priority": 88,
                    }
                )
            elif applied:
                actions.append(
                    {
                        "kind": "application_followup",
                        "title": "更新投递反馈",
                        "description": "记录平台、投递日期、HR 联系方式和反馈，避免投递后失联。",
                        "href": "/applications",
                        "priority": 82,
                    }
                )
            elif active:
                actions.append(
                    {
                        "kind": "application_followup",
                        "title": "跟进进行中的投递",
                        "description": "优先处理状态最近变化的岗位，并准备下一轮沟通。",
                        "href": "/applications",
                        "priority": 78,
                    }
                )

        latest_report = (interviews[0].report if interviews and isinstance(interviews[0].report, dict) else {}) if interviews else {}
        weak_score = latest_report.get("average_feedback_score") or latest_report.get("overall_score")
        if not interviews or (isinstance(weak_score, (int, float)) and weak_score < 75):
            actions.append(
                {
                    "kind": "interview_practice",
                    "title": "再练一轮面试",
                    "description": "围绕岗位和简历交集继续练追问，补齐表达证据。",
                    "href": "/interview/start",
                    "priority": 72,
                }
            )

        score_report = latest_resume.score_report or {}
        risks = list(score_report.get("risks") or [])
        if risks:
            actions.append(
                {
                    "kind": "resume_advice",
                    "title": "修正简历短板",
                    "description": str(risks[0])[:80],
                    "href": "/resume/upload",
                    "priority": 68,
                }
            )

        actions.sort(key=lambda item: int(item["priority"]), reverse=True)
        return actions[:4]
