from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from config import settings
from states import AuthStates

router = Router()

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.set_state(AuthStates.WAIT_PASSWORD)
    await message.answer("Введите пароль:")

@router.message(AuthStates.WAIT_PASSWORD)
async def password_handler(message: Message, state: FSMContext):
    if message.text and message.text.strip() == settings.admin_password:
        await state.clear()
        await message.answer(
            "Добро пожаловать.\n"
            "Опишите задачу текстом (голос в проекте не используется).\n"
            "Чтобы отменить уже отправленную задачу, напишите: ОТМЕНИТЬ ЗАДАЧУ"
        )
        # Переходим в общий поток ввода задачи
        from states import TaskStates
        await state.set_state(TaskStates.WAIT_TEXT)
    else:
        await message.answer("Неверный пароль, попробуйте снова.")