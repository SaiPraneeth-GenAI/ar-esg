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
  underlying figures) are never re-billed -- cached by a hash of the exact
  JSON sent to the model, so a repeat dashboard load or tab switch is free.
"""

import hashlib
import json
import logging

from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger("dashboard_insight")

_MODEL = "gpt-4o-mini"
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


def _cache_key(context: dict) -> str:
    raw = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_dashboard_insight(context: dict, fallback: str | None) -> str | None:
    """context is a plain-JSON-serializable dict of already-computed figures
    (current/prior values, deltas, top contributors, target statuses).
    Returns the AI summary, or `fallback` (the existing rule-based sentence)
    on any error -- callers should always pass a fallback so the card never
    ends up empty."""
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback

    key = _cache_key(context)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=_TIMEOUT_SECONDS, max_retries=1)
        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.2,
            max_tokens=_MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, default=str)},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return fallback
        _CACHE[key] = text
        return text
    except Exception:
        logger.exception("dashboard_insight generation failed, falling back to rule-based text")
        return fallback
