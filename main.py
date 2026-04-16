import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from db import engine
from handlers.auth import router as auth_router
from handlers.task import router as task_router
from models import Base
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)


async def init_db():
    # Создаём таблицы автоматически при первом запуске
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def main():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан в окружении/ .env")
    if not settings.db_url:
        raise RuntimeError("DB_URL не задан в окружении/ .env")

    await init_db()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(auth_router)
    dp.include_router(task_router)

    scheduler = setup_scheduler()
    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)

if __name__ == "__main__":
    asyncio.run(main())