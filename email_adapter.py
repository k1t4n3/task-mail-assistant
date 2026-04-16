from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from typing import Literal

import aiosmtplib

from config import settings
from date_display import RUS_DOW

ReminderKind = Literal["assignment", "day_before", "day_of", "overdue", "cancelled"]


def _format_deadline_ru(deadline_at: datetime) -> str:
    tz = ZoneInfo(settings.app_timezone)
    dt = deadline_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone(tz)
    dow = RUS_DOW.get(dt_local.weekday(), "")
    return f"{dt_local.strftime('%d.%m.%Y %H:%M')} ({dow})"


async def _send_raw(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_port or not settings.smtp_from:
        raise RuntimeError("SMTP не настроен: задайте SMTP_HOST, SMTP_PORT, SMTP_FROM в .env")

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")

    port = int(settings.smtp_port)
    if settings.smtp_use_ssl:
        client = aiosmtplib.SMTP(hostname=settings.smtp_host, port=port, use_tls=True)
    else:
        start_tls = None if settings.smtp_use_tls else False
        client = aiosmtplib.SMTP(
            hostname=settings.smtp_host,
            port=port,
            start_tls=start_tls,
        )
    await client.connect()
    try:
        if settings.smtp_user and settings.smtp_password:
            await client.login(settings.smtp_user, settings.smtp_password)
        await client.send_message(msg)
    finally:
        await client.quit()


async def send_task_assignment_emails(
    *,
    recipients: list[dict[str, str]],
    task_text: str,
    deadline_at: datetime,
) -> int:
    """Письмо каждому адресату: постановка задачи."""
    sent = 0
    dl = _format_deadline_ru(deadline_at)
    for r in recipients:
        email = (r.get("email") or "").strip()
        name = r.get("name") or email
        if not email:
            continue
        body = (
            f"Здравствуйте, {name}.\n\n"
            f"Вам поставлена задача:\n{task_text}\n\n"
            f"Срок: {dl}\n"
        )
        await _send_raw(email, "Постановка задачи", body)
        sent += 1
    return sent


async def send_reminder_emails(
    *,
    recipients: list[dict[str, str]],
    task_text: str,
    deadline_at: datetime,
    kind: ReminderKind,
) -> int:
    if kind == "assignment":
        return await send_task_assignment_emails(
            recipients=recipients, task_text=task_text, deadline_at=deadline_at
        )

    dl = _format_deadline_ru(deadline_at)
    if kind == "day_before":
        subj = "Напоминание: завтра срок задачи"
        intro = "Напоминаем: завтра наступает срок по задаче."
    elif kind == "day_of":
        subj = "Напоминание: сегодня срок задачи"
        intro = "Напоминаем: сегодня срок по задаче."
    elif kind == "overdue":
        subj = "Задача просрочена"
        intro = "Срок по задаче истёк. Это одно уведомление на следующий календарный день после дедлайна."
    else:
        subj = "Уведомление по задаче"
        intro = "Уведомление по задаче."

    sent = 0
    for r in recipients:
        email = (r.get("email") or "").strip()
        name = r.get("name") or email
        if not email:
            continue
        body = (
            f"Здравствуйте, {name}.\n\n"
            f"{intro}\n\n"
            f"Задача:\n{task_text}\n\n"
            f"Срок: {dl}\n"
        )
        await _send_raw(email, subj, body)
        sent += 1
    return sent


async def send_task_cancelled_emails(
    *,
    recipients: list[dict[str, str]],
    task_text: str,
    deadline_at: datetime,
) -> int:
    sent = 0
    dl = _format_deadline_ru(deadline_at)
    for r in recipients:
        email = (r.get("email") or "").strip()
        name = r.get("name") or email
        if not email:
            continue
        body = (
            f"Здравствуйте, {name}.\n\n"
            f"Задача отменена руководителем.\n\n"
            f"Была задача:\n{task_text}\n\n"
            f"Был срок: {dl}\n"
        )
        await _send_raw(email, "Задача отменена", body)
        sent += 1
    return sent
