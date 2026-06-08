from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class ScheduledTaskIntent:
    handled: bool
    action: str | None = None
    confidence: float = 0.0
    reply: str = ""
    title: str = ""
    instruction: str = ""
    schedule_type: str | None = None
    schedule_value: dict = field(default_factory=dict)
    next_run_at_utc: datetime | None = None
    next_run_at_local: str | None = None
    timezone: str = "Asia/Shanghai"
    selector: str | None = None


class ScheduledTaskIntentDetector:
    LIST_PATTERNS = ("列出", "查看", "我的定时", "任务列表", "有哪些任务")
    CANCEL_PATTERNS = ("取消任务", "删除任务", "停止任务")
    PAUSE_PATTERNS = ("暂停任务", "先停一下任务")
    RESUME_PATTERNS = ("恢复任务", "继续任务", "启用任务")

    def detect(self, message: str, *, now: datetime | None = None, timezone_name: str = "Asia/Shanghai") -> ScheduledTaskIntent:
        text = " ".join(str(message or "").strip().split())
        if not text:
            return ScheduledTaskIntent(handled=False)
        local_now, tz = self._local_now(now=now, timezone_name=timezone_name)

        # 先识别列表/暂停/恢复/取消，避免“取消明天任务”被误当成新建提醒。
        command = self._detect_management_command(text=text, timezone_name=timezone_name)
        if command.handled:
            return command

        if not self._looks_like_create(text):
            return ScheduledTaskIntent(handled=False)

        # 创建任务按确定性从高到低解析：显式 cron、相对时间、间隔、每周、工作日、每天、单次。
        cron = self._parse_explicit_cron(text=text, local_now=local_now, timezone_name=timezone_name)
        if cron.handled:
            return cron

        relative = self._parse_relative_once(text=text, local_now=local_now, timezone_name=timezone_name)
        if relative.handled:
            return relative

        interval = self._parse_interval(text=text, local_now=local_now, timezone_name=timezone_name)
        if interval.handled:
            return interval

        weekly = self._parse_weekly_cron(text=text, local_now=local_now, timezone_name=timezone_name)
        if weekly.handled:
            return weekly

        workday = self._parse_workday_cron(text=text, local_now=local_now, timezone_name=timezone_name)
        if workday.handled:
            return workday

        daily = self._parse_daily(text=text, local_now=local_now, timezone_name=timezone_name)
        if daily.handled:
            return daily

        once = self._parse_once(text=text, local_now=local_now, timezone_name=timezone_name)
        if once.handled:
            return once

        return ScheduledTaskIntent(
            handled=True,
            action="clarify",
            confidence=0.5,
            reply="我可以帮你创建定时任务，但还缺少明确时间。请告诉我是一次性、每天、每周，还是每隔多久执行。",
            timezone=timezone_name,
        )

    def _detect_management_command(self, *, text: str, timezone_name: str) -> ScheduledTaskIntent:
        if any(token in text for token in self.LIST_PATTERNS):
            return ScheduledTaskIntent(handled=True, action="list", confidence=0.95, timezone=timezone_name)
        for action, patterns in (("cancel", self.CANCEL_PATTERNS), ("pause", self.PAUSE_PATTERNS), ("resume", self.RESUME_PATTERNS)):
            if any(token in text for token in patterns):
                selector = self._selector_from_text(text)
                if not selector:
                    return ScheduledTaskIntent(handled=True, action="clarify", confidence=0.65, reply="请告诉我要操作哪一个任务，可以发任务 ID 的前 8 位。", timezone=timezone_name)
                return ScheduledTaskIntent(handled=True, action=action, selector=selector, confidence=0.9, timezone=timezone_name)
        return ScheduledTaskIntent(handled=False)

    def _parse_explicit_cron(self, *, text: str, local_now: datetime, timezone_name: str) -> ScheduledTaskIntent:
        match = re.search(r"(?:cron\s*[:：]?\s*)?((?:\S+\s+){4}\S+)", text, flags=re.IGNORECASE)
        if not match:
            return ScheduledTaskIntent(handled=False)
        expr = match.group(1).strip()
        if not self._looks_like_cron(expr):
            return ScheduledTaskIntent(handled=False)
        instruction = self._clean_instruction(text.replace(expr, "")) or "执行定时任务"
        return self._build_create(
            title=self._title_from_instruction(instruction),
            instruction=instruction,
            schedule_type="cron",
            schedule_value={"cron_expr": expr},
            next_local=self._next_cron_run(expr, local_now),
            confidence=0.86,
            timezone_name=timezone_name,
        )

    def _parse_interval(self, *, text: str, local_now: datetime, timezone_name: str) -> ScheduledTaskIntent:
        match = re.search(r"每\s*(?:隔\s*)?(\d+|[一二两三四五六七八九十]+|半)?\s*(秒|分钟|小时|天)", text)
        if not match:
            return ScheduledTaskIntent(handled=False)
        amount = self._amount_to_number(match.group(1) or "1", unit=match.group(2))
        unit = match.group(2)
        multiplier = {"秒": 1, "分钟": 60, "小时": 3600, "天": 86400}[unit]
        seconds = int(amount * multiplier)
        instruction = self._clean_instruction(text[match.end() :]) or self._clean_instruction(text[: match.start()]) or "执行定时任务"
        return self._build_create(
            title=self._title_from_instruction(instruction),
            instruction=instruction,
            schedule_type="interval",
            schedule_value={"seconds": seconds},
            next_local=local_now + timedelta(seconds=seconds),
            confidence=0.88,
            timezone_name=timezone_name,
        )

    def _parse_relative_once(self, *, text: str, local_now: datetime, timezone_name: str) -> ScheduledTaskIntent:
        match = re.search(r"(\d+|[一二两三四五六七八九十]+|半)\s*(秒|分钟|小时|天)\s*后", text)
        if not match:
            return ScheduledTaskIntent(handled=False)
        amount = self._amount_to_number(match.group(1), unit=match.group(2))
        unit = match.group(2)
        multiplier = {"秒": 1, "分钟": 60, "小时": 3600, "天": 86400}[unit]
        seconds = int(amount * multiplier)
        if seconds <= 0:
            return ScheduledTaskIntent(handled=False)
        instruction = self._clean_instruction(text[match.end() :]) or self._clean_instruction(text[: match.start()]) or "执行定时任务"
        return self._build_create(
            title=self._title_from_instruction(instruction),
            instruction=instruction,
            schedule_type="once",
            schedule_value={"run_at": (local_now + timedelta(seconds=seconds)).isoformat()},
            next_local=local_now + timedelta(seconds=seconds),
            confidence=0.84,
            timezone_name=timezone_name,
        )

    def _parse_weekly_cron(self, *, text: str, local_now: datetime, timezone_name: str) -> ScheduledTaskIntent:
        match = re.search(r"每周\s*([一二三四五六日天1-7])", text)
        if not match:
            return ScheduledTaskIntent(handled=False)
        hour, minute = self._time_from_text(text)
        if hour is None:
            return ScheduledTaskIntent(handled=False)
        dow = self._weekday_to_cron(match.group(1))
        expr = f"{minute or 0} {hour} * * {dow}"
        instruction = self._clean_instruction(text.replace(match.group(0), "")) or "执行定时任务"
        return self._build_create(
            title=self._title_from_instruction(instruction),
            instruction=instruction,
            schedule_type="cron",
            schedule_value={"cron_expr": expr},
            next_local=self._next_cron_run(expr, local_now),
            confidence=0.86,
            timezone_name=timezone_name,
        )

    def _parse_workday_cron(self, *, text: str, local_now: datetime, timezone_name: str) -> ScheduledTaskIntent:
        if "工作日" not in text:
            return ScheduledTaskIntent(handled=False)
        hour, minute = self._time_from_text(text)
        if hour is None:
            return ScheduledTaskIntent(handled=False)
        expr = f"{minute or 0} {hour} * * 1-5"
        instruction = self._clean_instruction(text.replace("工作日", "")) or "执行定时任务"
        return self._build_create(
            title=self._title_from_instruction(instruction),
            instruction=instruction,
            schedule_type="cron",
            schedule_value={"cron_expr": expr},
            next_local=self._next_cron_run(expr, local_now),
            confidence=0.86,
            timezone_name=timezone_name,
        )

    def _parse_daily(self, *, text: str, local_now: datetime, timezone_name: str) -> ScheduledTaskIntent:
        if "每天" not in text and "每日" not in text:
            return ScheduledTaskIntent(handled=False)
        hour, minute = self._time_from_text(text)
        if hour is None:
            return ScheduledTaskIntent(handled=False)
        next_local = local_now.replace(hour=hour, minute=minute or 0, second=0, microsecond=0)
        if next_local <= local_now:
            next_local += timedelta(days=1)
        instruction = self._clean_instruction(text.replace("每天", "").replace("每日", "")) or "执行定时任务"
        return self._build_create(
            title=self._title_from_instruction(instruction),
            instruction=instruction,
            schedule_type="cron",
            schedule_value={"cron_expr": f"{minute or 0} {hour} * * *"},
            next_local=next_local,
            confidence=0.84,
            timezone_name=timezone_name,
        )

    def _parse_once(self, *, text: str, local_now: datetime, timezone_name: str) -> ScheduledTaskIntent:
        hour, minute = self._time_from_text(text)
        if hour is None:
            return ScheduledTaskIntent(handled=False)
        base = local_now
        if "后天" in text:
            base += timedelta(days=2)
        elif "明天" in text:
            base += timedelta(days=1)
        next_local = base.replace(hour=hour, minute=minute or 0, second=0, microsecond=0)
        if "今天" in text and next_local <= local_now:
            return ScheduledTaskIntent(handled=True, action="clarify", confidence=0.55, reply="这个时间今天已经过了，请确认要改成明天还是另一个时间。", timezone=timezone_name)
        if "明天" not in text and "后天" not in text and "今天" not in text and next_local <= local_now:
            next_local += timedelta(days=1)
        instruction = self._clean_instruction(text) or "提醒我"
        return self._build_create(
            title=self._title_from_instruction(instruction),
            instruction=instruction,
            schedule_type="once",
            schedule_value={"run_at": next_local.isoformat()},
            next_local=next_local,
            confidence=0.82,
            timezone_name=timezone_name,
        )

    def _build_create(
        self,
        *,
        title: str,
        instruction: str,
        schedule_type: str,
        schedule_value: dict,
        next_local: datetime,
        confidence: float,
        timezone_name: str,
    ) -> ScheduledTaskIntent:
        return ScheduledTaskIntent(
            handled=True,
            action="create",
            confidence=confidence,
            title=title,
            instruction=instruction,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            next_run_at_local=next_local.replace(tzinfo=None).isoformat(timespec="seconds"),
            next_run_at_utc=self._to_utc_naive(next_local, timezone_name=timezone_name),
            timezone=timezone_name,
        )

    @staticmethod
    def _looks_like_create(text: str) -> bool:
        return any(
            token in text
            for token in (
                "提醒",
                "定时",
                "闹钟",
                "叫我",
                "每天",
                "每周",
                "每隔",
                "每 ",
                "工作日",
                "后提醒",
                "分钟后",
                "小时后",
                "秒后",
                "天后",
                "cron",
                "Cron",
            )
        )

    @staticmethod
    def _looks_like_cron(expr: str) -> bool:
        parts = expr.split()
        if len(parts) != 5:
            return False
        allowed = re.compile(r"^[\d*/,-]+$")
        return all(bool(allowed.match(part)) for part in parts)

    @staticmethod
    def _selector_from_text(text: str) -> str | None:
        matches = re.findall(r"[0-9a-fA-F]{6,36}", text)
        return matches[-1] if matches else None

    @staticmethod
    def _time_from_text(text: str) -> tuple[int | None, int | None]:
        match = re.search(r"(上午|早上|下午|晚上|中午)?\s*(\d{1,2})\s*(?:点|:|：)\s*(\d{1,2})?", text)
        if not match:
            return None, None
        period, hour_text, minute_text = match.groups()
        hour = int(hour_text)
        minute = int(minute_text or 0)
        if period in {"下午", "晚上"} and hour < 12:
            hour += 12
        if period == "中午" and hour < 11:
            hour += 12
        if period in {"上午", "早上"} and hour == 12:
            hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None, None
        return hour, minute

    @staticmethod
    def _clean_instruction(text: str) -> str:
        cleaned = re.sub(r"cron\s*[:：]?", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"每周\s*[一二三四五六日天1-7]", "", cleaned)
        cleaned = re.sub(r"(?:今天|明天|后天|每天|每日|工作日|上午|早上|下午|晚上|中午)?\s*\d{1,2}\s*(?:点|:|：)\s*\d{0,2}", "", cleaned)
        cleaned = re.sub(r"每\s*(?:隔\s*)?(?:\d+|[一二两三四五六七八九十]+|半)?\s*(?:秒|分钟|小时|天)", "", cleaned)
        cleaned = re.sub(r"(?:\d+|[一二两三四五六七八九十]+|半)\s*(?:秒|分钟|小时|天)\s*后", "", cleaned)
        cleaned = re.sub(r"今天|明天|后天|提醒我|提醒|帮我|定时|闹钟|叫我|请|到时候", "", cleaned)
        return " ".join(cleaned.strip(" ，。,.：:").split())

    @staticmethod
    def _title_from_instruction(instruction: str) -> str:
        value = instruction.strip() or "定时任务"
        return value[:32]

    @staticmethod
    def _local_now(*, now: datetime | None, timezone_name: str) -> tuple[datetime, ZoneInfo]:
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("Asia/Shanghai")
        if now is None:
            return datetime.now(tz).replace(tzinfo=None), tz
        if now.tzinfo is not None:
            return now.astimezone(tz).replace(tzinfo=None), tz
        return now.replace(tzinfo=None), tz

    @staticmethod
    def _amount_to_number(value: str, *, unit: str) -> float:
        text = str(value or "").strip()
        if text == "半":
            return 0.5
        if text.isdigit():
            return float(int(text))
        digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if text == "十":
            return 10
        if text.startswith("十"):
            return float(10 + digits.get(text[-1], 0))
        if text.endswith("十"):
            return float(digits.get(text[0], 1) * 10)
        if "十" in text:
            left, right = text.split("十", 1)
            return float(digits.get(left, 1) * 10 + digits.get(right, 0))
        return float(digits.get(text, 1))

    @staticmethod
    def _weekday_to_cron(value: str) -> int:
        return {"一": 1, "1": 1, "二": 2, "2": 2, "三": 3, "3": 3, "四": 4, "4": 4, "五": 5, "5": 5, "六": 6, "6": 6, "日": 7, "天": 7, "7": 7}[value]

    @staticmethod
    def _to_utc_naive(local_dt: datetime, *, timezone_name: str) -> datetime:
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("Asia/Shanghai")
        return local_dt.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None)

    def _next_cron_run(self, expr: str, local_now: datetime) -> datetime:
        minute_expr, hour_expr, day_expr, month_expr, dow_expr = expr.split()
        current = local_now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(366 * 24 * 60):
            if (
                self._field_matches(current.minute, minute_expr)
                and self._field_matches(current.hour, hour_expr)
                and self._field_matches(current.day, day_expr)
                and self._field_matches(current.month, month_expr)
                and self._dow_matches(current, dow_expr)
            ):
                return current
            current += timedelta(minutes=1)
        raise ValueError("cron expression has no next run within one year")

    @staticmethod
    def _field_matches(value: int, expr: str) -> bool:
        if expr == "*":
            return True
        for part in expr.split(","):
            if "/" in part:
                base, step_text = part.split("/", 1)
                step = int(step_text)
                if base == "*" and value % step == 0:
                    return True
            elif "-" in part:
                start, end = [int(item) for item in part.split("-", 1)]
                if start <= value <= end:
                    return True
            elif part.isdigit() and value == int(part):
                return True
        return False

    def _dow_matches(self, value: datetime, expr: str) -> bool:
        if expr == "*":
            return True
        cron_dow = value.weekday() + 1
        return self._field_matches(cron_dow, expr)
