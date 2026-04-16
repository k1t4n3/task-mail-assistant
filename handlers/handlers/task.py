from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from states import TaskStates
from llm_adapter import parse_to_confirmation

router = Router()

@router.message(TaskStates.WAIT_TEXT)
async def task_text_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пришлите текст задачи.")
        return

    parsed = parse_to_confirmation(text)
    await state.update_data(
        raw_text=text,
        parsed=parsed,
    )
    recipients_preview = ", ".join(parsed["recipients_surnames"])
    await message.answer(
        "Задача понята. Проверьте:\n"
        f"Адресаты (фамилии): {recipients_preview}\n"
        f"Срок: {parsed['deadline_at_iso']}\n"
        f"Текст: {parsed['task_text']}\n\n"
        "Команды: ОТПРАВИТЬ или ОТМЕНА"
    )
    await state.set_state(TaskStates.WAIT_CONFIRM)

@router.message(TaskStates.WAIT_CONFIRM)
async def confirm_handler(message: Message, state: FSMContext):
    cmd = (message.text or "").strip().upper()

    data = await state.get_data()
    parsed = data.get("parsed")

    if cmd == "ОТМЕНА":
        await state.clear()
        await message.answer("Ок, отменено. Опишите задачу снова:")
        from states import TaskStates
        await state.set_state(TaskStates.WAIT_TEXT)
        return

    if cmd == "ОТПРАВИТЬ":
        # На Day 1 не отправляем почту и не пишем в БД — пока только “успешный шаг”.
        await state.clear()
        await message.answer("ОТПРАВИТЬ принято. На Day 7 тут будет отправка писем и запись задачи в БД.")
        return

    await message.answer("Не понял. Напишите ОТПРАВИТЬ или ОТМЕНА.")