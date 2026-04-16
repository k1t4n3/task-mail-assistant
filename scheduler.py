from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from config import settings
from db import SessionLocal
from email_adapter import send_reminder_emails
from models import Task, TaskStatus

logger = logging.getLogger(__name__)


async def _reminder_tick() -> None:
    if not settings.reminders_enabled:
        return
    if not settings.smtp_host or not settings.smtp_from:
        return

    tz = ZoneInfo(settings.app_timezone)
    now = datetime.now(tz)
    today = now.date()

    async with SessionLocal() as session:
        result = await session.execute(
            select(Task).where(Task.status == TaskStatus.SENT.value)
        )
        tasks = result.scalars().all()

        for task in tasks:
            rs = dict(task.reminders_sent or {})
            dl = task.deadline_at
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            dl_local = dl.astimezone(tz)
            d_deadline = dl_local.date()

            recipients = task.recipients or []

            try:
                if not rs.get("day_before") and today == d_deadline - timedelta(days=1):
                    await send_reminder_emails(
                        recipients=recipients,
                        task_text=task.task_text,
                        deadline_at=dl,
                        kind="day_before",
                    )
                    rs["day_before"] = True
                    task.reminders_sent = rs
                    await session.commit()
                    continue

                if not rs.get("day_of") and today == d_deadline:
                    await send_reminder_emails(
                        recipients=recipients,
                        task_text=task.task_text,
                        deadline_at=dl,
                        kind="day_of",
                    )
                    rs["day_of"] = True
                    task.reminders_sent = rs
                    await session.commit()
                    continue

                if not rs.get("overdue") and today == d_deadline + timedelta(days=1):
                    await send_reminder_emails(
                        recipients=recipients,
                        task_text=task.task_text,
                        deadline_at=dl,
                        kind="overdue",
                    )
                    rs["overdue"] = True
                    task.reminders_sent = rs
                    await session.commit()
            except Exception as e:  # noqa: BLE001
                logger.exception("Reminder failed for task %s: %s", task.id, e)
                await session.rollback()


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _reminder_tick,
        "interval",
        minutes=15,
        id="email_reminders",
        replace_existing=True,
    )
    return scheduler
