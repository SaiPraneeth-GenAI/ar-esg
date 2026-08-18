"""AI-generated dashboard insight -- a short, guardrailed business summary of
what improved and what needs attention to hit committed targets, replacing
the purely rule-based one-liner on the Carbon overview card.

Guardrails, because this text is shown to the client unreviewed:
- The model only ever sees a JSON object of numbers this backend already
  computed (the same figures the cards/pies show) -- it never sees raw
  entries, free text, or anything it could misquote.
- The system prompt forbids inventing any figure, comparison, or cause not
  present in that JSON, and forbids generic advice not tied to the numbers.
- Any failure (timeout, malformed response, no API key) falls back to the
  existing deterministic, rule-based sentence -- the card never goes blank
  and never blocks on the AI call being slow.
- Identical inputs (same tenant/location/period/period_mode and the same
  underlying figures) are never re-billed. Two layers: an in-process dict
  for same-worker repeats within a warm process, and carbon_insight (a DB
  table) as the durable source of truth -- callers should always check
  get_cached_insight() first and only call generate_dashboard_insight() on
  a miss, then persist the result with store_insight() (see carbon.py's
  /ai-insight route). A fallback (non-AI) response is never persisted, so a
  transient OpenAI outage self-heals on the next request instead of
  permanently freezing the cache on rule-based text.
"""

import hashlib
import json
import logging
import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import CarbonInsight
from openai import OpenAI

logger = logging.getLogger("dashboard_insight")

MODEL = "gpt-4o-mini"
_TIMEOUT_SECONDS = 20
_MAX_OUTPUT_TOKENS = 260
_CACHE: dict[str, str] = {}

_SYSTEM_PROMPT = """You are an ESG performance analyst writing a short insight for a company's sustainability dashboard.

Rules you must follow exactly:
- Use ONLY the figures in the JSON you are given. Never invent a number, percentage, cause, or comparison that is not present in it.
- Do not give generic sustainability advice that isn't tied to the specific numbers provided.
- Write at most 4 sentences of plain business English. No bullet points, no markdown, no headings.
- Cover, only where the data supports it: (1) what improved this period, in concrete terms, and (2) which tracked target most needs attention to stay on track, naming it and its exact status label.
- If "targets" is empty, say plainly that no targets are currently tracked -- do not guess at one.
- If the numbers are too sparse to say anything meaningful, respond with exactly: "Not enough data yet to generate an insight for this period."
"""


def hash_context(context: dict) -> str:
    raw = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached_insight(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date, period_mode: str, input_hash: str
) -> str | None:
    """The durable check: a row exists for this exact (tenant, location,
    period, period_mode) AND its stored hash matches today's figures. A
    match means the underlying data hasn't changed since it was generated
    -- return the stored text with no AI call at all."""
    row = (
        db.query(CarbonInsight)
        .filter(
            CarbonInsight.tenant_id == tenant_id,
            CarbonInsight.location_id == location_id,
            CarbonInsight.period == period,
            CarbonInsight.period_mode == period_mode,
        )
        .first()
    )
    if row is not None and row.input_hash == input_hash:
        return row.insight_text
    return None


def store_insight(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date, period_mode: str, input_hash: str, text: str
) -> None:
    """Overwrites the one row for this (tenant, location, period,
    period_mode) -- history isn't kept, only the latest text for the latest
    hash. Caller commits (or not) as part of its own request transaction."""
    row = (
        db.query(CarbonInsight)
        .filter(
            CarbonInsight.tenant_id == tenant_id,
            CarbonInsight.location_id == location_id,
            CarbonInsight.period == period,
            CarbonInsight.period_mode == period_mode,
        )
        .first()
    )
    if row is not None:
        row.input_hash = input_hash
        row.insight_text = text
        row.model = MODEL
        row.updated_at = datetime.utcnow()
    else:
        db.add(
            CarbonInsight(
                tenant_id=tenant_id,
                location_id=location_id,
                period=period,
                period_mode=period_mode,
                input_hash=input_hash,
                insight_text=text,
                model=MODEL,
            )
        )


def generate_dashboard_insight(context: dict, fallback: str | None) -> tuple[str | None, bool]:
    """context is a plain-JSON-serializable dict of already-computed figures
    (current/prior values, deltas, top contributors, target statuses).
    Returns (text, was_ai_generated) -- was_ai_generated is False whenever
    `text` is really just `fallback` (no API key, empty response, or an
    error), so callers know not to persist it as a durable cache hit."""
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback, False

    key = hash_context(context)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached, True

    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=_TIMEOUT_SECONDS, max_retries=1)
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.2,
            max_tokens=_MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, default=str)},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return fallback, False
        _CACHE[key] = text
        return text, True
    except Exception:
        logger.exception("dashboard_insight generation failed, falling back to rule-based text")
        return fallback, False
