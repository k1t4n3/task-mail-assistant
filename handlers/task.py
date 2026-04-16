from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import func, select

from date_display import format_deadline_display
from db import SessionLocal
from email_adapter import send_task_assignment_emails, send_task_cancelled_emails
from llm_adapter import parse_task_text
from models import Task, TaskStatus
from recipient_resolver import resolve_recipients_from_db
from states import TaskStates

router = Router()

MAX_ACTIVE_TASKS = 25
CANCEL_PHRASE = "ОТМЕНИТЬ ЗАДАЧУ"


async def _active_task_count(session, manager_tg_id: int) -> int:
    q = await session.execute(
        select(func.count()).select_from(Task).where(
            Task.manager_tg_id == manager_tg_id,
            Task.status == TaskStatus.SENT.value,
        )
    )
    return int(q.scalar_one())


async def _handle_task_text_value(*, message: Message, state: FSMContext, text: str) -> None:
    parsed = await parse_task_text(text)
    recipients_surnames: list[str] = parsed.get("recipients_surnames", [])
    task_text: str = parsed.get("task_text", "").strip()
    deadline_at_iso: str = parsed.get("deadline_at_iso", "")

    try:
        deadline_at = datetime.fromisoformat(deadline_at_iso.replace("Z", "+00:00"))
    except ValueError:
        deadline_at = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        recipients = await resolve_recipients_from_db(session, recipients_surnames)

    if not recipients:
        await message.answer("Не удалось определить адресатов. Укажите фамилии явно.")
        return

    await state.update_data(
        parsed=parsed,
        recipients=recipients,
        deadline_at_iso=deadline_at.isoformat(),
    )

    missing = [r["name"] for r in recipients if not (r.get("email") or "").strip()]
    warn = ""
    if missing:
        warn = (
            "\n\nВнимание: для "
            + ", ".join(missing)
            + " не найден email в справочнике (таблица recipients). Добавьте запись в БД."
        )

    recipients_display = ", ".join(
        r["name"] + (f" ({r['email']})" if r.get("email") else " (email не найден)")
        for r in recipients
    )
    await state.set_state(TaskStates.WAIT_CONFIRM)
    await message.answer(
        "Как понял:\n"
        f"Задача: {task_text}\n"
        f"Срок: {format_deadline_display(deadline_at)}\n"
        f"Адресаты: {recipients_display}\n\n"
        "Можно прислать ещё одно текстовое сообщение для уточнения до отправки.\n"
        "Действия: ОТПРАВИТЬ или ОТМЕНА (без писем адресатам)."
        f"{warn}"
    )


async def _handle_task_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пришлите текст задачи.")
        return
    await _handle_task_text_value(message=message, state=state, text=message.text)


@router.message(TaskStates.WAIT_TEXT)
async def task_text_handler(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.upper() == CANCEL_PHRASE:
        await _start_cancel_flow(message, state)
        return
    await _handle_task_text(message, state)


@router.message(TaskStates.WAIT_TEXT, F.voice)
async def task_voice_not_supported(message: Message) -> None:
    await message.answer(
        "Голосовой ввод в этом проекте не используется (по заданию — только текст). "
        "Опишите задачу текстом."
    )


@router.message(TaskStates.WAIT_CONFIRM)
async def confirm_text_handler(message: Message, state: FSMContext) -> None:
    raw_u = (message.text or "").strip().upper()
    if raw_u == CANCEL_PHRASE:
        await message.answer(
            "Сейчас экран подтверждения черновика. Сначала напишите ОТМЕНА или ОТПРАВИТЬ. "
            "Отмену уже отправленной задачи можно сделать командой «ОТМЕНИТЬ ЗАДАЧУ» на шаге ввода задачи."
        )
        return

    text = raw_u
    if text == "ОТМЕНА":
        await state.clear()
        await state.set_state(TaskStates.WAIT_TEXT)
        await message.answer("Отменено без отправки почты. Опишите задачу заново:")
        return

    if text == "ОТПРАВИТЬ":
        data: dict[str, Any] = await state.get_data()
        recipients = list(data.get("recipients") or [])
        task_text = (data.get("parsed", {}) or {}).get("task_text", "").strip()
        deadline_at_iso = data.get("deadline_at_iso", "")

        try:
            deadline_at = datetime.fromisoformat(deadline_at_iso.replace("Z", "+00:00"))
        except ValueError:
            deadline_at = datetime.now(timezone.utc)

        bad = [r for r in recipients if not (r.get("email") or "").strip()]
        if bad:
            await message.answer(
                "Нельзя отправить: у части адресатов нет email в справочнике. "
                "Добавьте записи в таблицу `recipients` в pgAdmin и повторите ввод/уточнение."
            )
            return

        manager_tg_id = message.from_user.id if message.from_user else 0

        async with SessionLocal() as session:
            n = await _active_task_count(session, manager_tg_id)
            if n >= MAX_ACTIVE_TASKS:
                await message.answer(
                    f"Достигнут лимит активных задач ({MAX_ACTIVE_TASKS}). "
                    "Отмените одну через «ОТМЕНИТЬ ЗАДАЧУ» или дождитесь закрытия сроков."
                )
                return

        try:
            await send_task_assignment_emails(
                recipients=recipients,
                task_text=task_text,
                deadline_at=deadline_at,
            )
        except Exception as e:  # noqa: BLE001
            await message.answer(f"Ошибка отправки почты (проверьте SMTP в .env): {e}")
            return

        rs = {"assignment": True, "day_before": False, "day_of": False, "overdue": False}
        async with SessionLocal() as session:
            task = Task(
                manager_tg_id=manager_tg_id,
                recipients=recipients,
                task_text=task_text,
                deadline_at=deadline_at,
                status=TaskStatus.SENT.value,
                reminders_sent=rs,
            )
            session.add(task)
            await session.commit()

        await state.clear()
        await state.set_state(TaskStates.WAIT_TEXT)
        await message.answer(
            f"Задача отправлена адресатам по почте ({len(recipients)}). "
            "Можно поставить следующую задачу или написать «ОТМЕНИТЬ ЗАДАЧУ»."
        )
        return

    await _handle_task_text(message, state)


@router.message(TaskStates.WAIT_CONFIRM, F.voice)
async def confirm_voice_not_supported(message: Message) -> None:
    await message.answer("Голос не используется. Уточните задачу текстом или напишите ОТПРАВИТЬ/ОТМЕНА.")


async def _start_cancel_flow(message: Message, state: FSMContext) -> None:
    manager_tg_id = message.from_user.id if message.from_user else 0
    async with SessionLocal() as session:
        result = await session.execute(
            select(Task)
            .where(
                Task.manager_tg_id == manager_tg_id,
                Task.status == TaskStatus.SENT.value,
            )
            .order_by(Task.id.desc())
            .limit(MAX_ACTIVE_TASKS)
        )
        rows = result.scalars().all()

    if not rows:
        await message.answer("Нет активных задач для отмены.")
        return

    lines = []
    ids: list[int] = []
    for i, t in enumerate(rows, start=1):
        ids.append(t.id)
        preview = (t.task_text or "").replace("\n", " ")[:60]
        dl = format_deadline_display(t.deadline_at.astimezone())
        lines.append(f"{i}) {preview} — до {dl}")

    await state.set_state(TaskStates.WAIT_CANCEL_SELECT)
    await state.update_data(cancel_task_ids=ids)
    await message.answer(
        "Активные задачи (до 25). Ответьте номером строки для отмены:\n\n"
        + "\n".join(lines)
        + "\n\nДля отмены этой операции напишите 0."
    )


@router.message(TaskStates.WAIT_CANCEL_SELECT)
async def cancel_pick_handler(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.upper() == "ОТМЕНА":
        raw = "0"

    if not raw.isdigit():
        await message.answer("Пришлите номер задачи из списка (число) или 0.")
        return

    n = int(raw)
    data = await state.get_data()
    ids: list[int] = data.get("cancel_task_ids") or []

    if n == 0:
        await state.set_state(TaskStates.WAIT_TEXT)
        await state.update_data(cancel_task_ids=[])
        await message.answer("Отмена выбора. Опишите задачу или снова «ОТМЕНИТЬ ЗАДАЧУ».")
        return

    if n < 1 or n > len(ids):
        await message.answer("Неверный номер. Повторите.")
        return

    task_id = ids[n - 1]
    manager_tg_id = message.from_user.id if message.from_user else 0

    async with SessionLocal() as session:
        result = await session.execute(
            select(Task).where(
                Task.id == task_id,
                Task.manager_tg_id == manager_tg_id,
                Task.status == TaskStatus.SENT.value,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            await message.answer("Задача не найдена или уже снята.")
            await state.set_state(TaskStates.WAIT_TEXT)
            await state.update_data(cancel_task_ids=[])
            return

        recipients = list(task.recipients or [])
        task_text = task.task_text
        deadline_at = task.deadline_at

        try:
            await send_task_cancelled_emails(
                recipients=recipients,
                task_text=task_text,
                deadline_at=deadline_at,
            )
        except Exception as e:  # noqa: BLE001
            await message.answer(f"Ошибка отправки писем об отмене: {e}")
            return

        task.status = TaskStatus.CANCELLED.value
        await session.commit()

    await state.set_state(TaskStates.WAIT_TEXT)
    await state.update_data(cancel_task_ids=[])
    await message.answer("Задача снята. Всем адресатам отправлено письмо об отмене.")
