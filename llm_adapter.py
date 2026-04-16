from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from dateutil import parser as date_parser

from config import settings


def normalize_surname(s: str) -> str:
    return re.sub(r"[^а-яА-ЯёЁa-zA-Z-]", "", (s or "").strip()).lower()


def _now_in_app_tz() -> datetime:
    tz = ZoneInfo(settings.app_timezone)
    return datetime.now(tz)


def _stub_extract_surnames(text: str) -> list[str]:
    lower = text.lower()
    known = ["иванов", "петрова", "сидоров"]
    found: list[str] = []
    for k in known:
        if re.search(rf"\b{k}", lower):
            found.append(k)
    if found:
        return found

    # Эвристика: фамилии до «:» или до «—», разделитель «и» / запятая
    head = text
    for sep in (":", "—", "-"):
        if sep in head:
            head = head.split(sep, 1)[0]
            break
    head = head.strip()
    if not head:
        return ["неизвестно"]

    parts = re.split(r"\s+и\s+|,\s*", head, flags=re.IGNORECASE)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        token = re.sub(r"^(передай|передать|нужно|сделать)\s+", "", p, flags=re.IGNORECASE).strip()
        m = re.match(r"^([А-ЯЁа-яёA-Za-z-]+)", token)
        if m:
            out.append(normalize_surname(m.group(1)))
    return out or ["неизвестно"]


def _stub_deadline(text: str) -> datetime:
    tz = ZoneInfo(settings.app_timezone)
    now = datetime.now(tz)
    lower = text.lower()

    if "завтра" in lower:
        d = (now.date() + timedelta(days=1))
        t = _parse_time_hint(lower, default_hour=18, default_minute=0)
        return datetime(d.year, d.month, d.day, t[0], t[1], tzinfo=tz)

    m = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if year < 100:
            year += 2000
        if (month, day) < (now.month, now.day) and not m.group(3):
            year = now.year + 1
        t = _parse_time_hint(lower, default_hour=12, default_minute=0)
        try:
            return datetime(year, month, day, t[0], t[1], tzinfo=tz)
        except ValueError:
            pass

    # dateutil для фраз вроде «15 марта»
    try:
        default = now.replace(hour=12, minute=0, second=0, microsecond=0)
        dt = date_parser.parse(text, default=default, dayfirst=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
        return dt
    except (ValueError, OverflowError, TypeError):
        pass

    return (now + timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)


def _parse_time_hint(lower: str, default_hour: int, default_minute: int) -> tuple[int, int]:
    m = re.search(r"к\s*(\d{1,2})(?::(\d{2}))?", lower)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        return h, mi
    if "18:00" in lower or "к 18" in lower:
        return 18, 0
    return default_hour, default_minute


def _stub_task_text(text: str) -> str:
    task_text = text.strip()
    if ":" in task_text:
        task_text = task_text.split(":", 1)[1].strip()
    if re.search(r"\bдо\b", task_text, flags=re.IGNORECASE):
        task_text = re.split(r"\bдо\b", task_text, flags=re.IGNORECASE, maxsplit=1)[0].strip()
    return task_text or text.strip()


def extract_task_stub(text: str) -> dict:
    surnames = _stub_extract_surnames(text)
    deadline_at = _stub_deadline(text)
    task_text = _stub_task_text(text)
    return {
        "recipients_surnames": surnames,
        "task_text": task_text,
        "deadline_at_iso": deadline_at.astimezone(timezone.utc).isoformat(),
    }


async def _parse_openai(text: str) -> dict | None:
    if not settings.openai_api_key:
        return None

    today = _now_in_app_tz().strftime("%Y-%m-%d %H:%M %Z")
    system = (
        "Ты извлекаешь из текста руководителя структурированные данные для постановки задачи. "
        "Ответь строго одним JSON-объектом без markdown с полями:\n"
        '- "recipients_surnames": массив строк — фамилии в именительном падеже, нижний регистр (например "иванов");\n'
        '- "task_text": краткая формулировка задачи для сотрудника на русском;\n'
        '- "deadline_at_iso": срок в ISO8601 с явным offset (например +03:00 или Z), '
        "интерпретируй относительно текущей даты пользователя.\n"
        f'Текущая дата/время (часовой пояс приложения): {today}.'
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    url = f"{settings.openai_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        obj = json.loads(content)
        surnames = obj.get("recipients_surnames") or []
        if isinstance(surnames, str):
            surnames = [surnames]
        task_text = str(obj.get("task_text") or "").strip()
        iso = str(obj.get("deadline_at_iso") or "").strip()
        if not task_text or not iso:
            return None
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return {
            "recipients_surnames": [normalize_surname(str(s)) for s in surnames if str(s).strip()],
            "task_text": task_text,
            "deadline_at_iso": dt.astimezone(timezone.utc).isoformat(),
        }
    except Exception:
        return None


async def parse_task_text(text: str) -> dict:
    """
    Извлечение адресатов, текста задачи и дедлайна.
    При LLM_PROVIDER=openai и заданном OPENAI_API_KEY — запрос к OpenAI-совместимому API.
    Иначе — локальный stub-парсер.
    """
    if settings.llm_provider == "openai":
        parsed = await _parse_openai(text)
        if parsed:
            return parsed
    return extract_task_stub(text)


def parse_to_confirmation(text: str) -> dict:
    """Синхронная обёртка для обратной совместимости (предпочтительно parse_task_text)."""
    return extract_task_stub(text)
