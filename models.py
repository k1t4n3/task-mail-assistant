import enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Text, JSON, Integer
from datetime import datetime


def _default_reminders_sent() -> dict:
    return {
        "assignment": False,
        "day_before": False,
        "day_of": False,
        "overdue": False,
    }


class Base(DeclarativeBase):
    pass


class TaskStatus(str, enum.Enum):
    DRAFT = "draft"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SENT = "sent"
    CANCELLED = "cancelled"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_tg_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # адресаты: [{ "name": "...", "email": "..."}, ...]
    recipients: Mapped[list] = mapped_column(JSON, nullable=False)

    task_text: Mapped[str] = mapped_column(Text, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(String(64), nullable=False, default=TaskStatus.DRAFT.value)

    # какие напоминания уже отправлены по почте
    reminders_sent: Mapped[dict] = mapped_column(JSON, nullable=False, default=_default_reminders_sent)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    surname: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)  # ключ для поиска
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str] = mapped_column(String(256), nullable=False)