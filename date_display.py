from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import settings

RUS_DOW = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}


def format_deadline_display(deadline_at: datetime) -> str:
    tz = ZoneInfo(settings.app_timezone)
    dt = deadline_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(tz)
    dow = RUS_DOW.get(dt.weekday(), dt.strftime("%A"))
    return f"{dt.strftime('%d.%m.%Y %H:%M')} ({dow})"
