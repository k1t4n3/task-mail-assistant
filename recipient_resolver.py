from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_adapter import normalize_surname
from models import Recipient


async def resolve_recipients_from_db(session: AsyncSession, surnames: list[str]) -> list[dict[str, str]]:
    """Сопоставление фамилий из LLM/парсера с таблицей recipients (фамилия -> email)."""
    if not surnames:
        return []

    norms = [normalize_surname(s) for s in surnames if s and str(s).strip()]
    norms = list(dict.fromkeys(norms))
    if not norms:
        return []

    result = await session.execute(select(Recipient).where(Recipient.surname.in_(norms)))
    rows = result.scalars().all()
    by_surname = {r.surname: r for r in rows}

    out: list[dict[str, str]] = []
    for raw in surnames:
        key = normalize_surname(raw)
        row = by_surname.get(key)
        if row:
            out.append({"name": row.full_name, "email": row.email, "surname_key": row.surname})
        else:
            out.append({"name": raw.strip() or key, "email": "", "surname_key": key})
    return out
