"""BRSR PDF -> peer metric extraction via GPT-4o-mini. A BRSR/annual report
runs to 100+ pages but only a handful actually state the ~16 figures this
platform compares; sending the whole document to the model would be slow
and needlessly expensive, so extract_relevant_text() first narrows it down
to pages that mention an ESG-relevant term and caps the total sent to the
model, keeping every extraction call small and cheap."""

import io
import json

from openai import OpenAI
from pypdf import PdfReader

from app.api.routes.charts import CHARTABLE_METRICS
from app.core.config import get_settings

_KEYWORDS = [
    "scope 1", "scope 2", "scope1", "scope2", "ghg", "greenhouse gas",
    "co2", "co2e", "tco2", "energy consum", "water consum", "water withdraw",
    "waste generat", "hazardous waste", "fatalit", "ltifr", "lost time injury",
    "driving training", "unsafe condition", "near miss", "brsr", "intensity",
    "turnover", "revenue",
]

_MAX_CHARS = 40_000  # keeps a single gpt-4o-mini call fast and cheap


def extract_relevant_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    matched: list[str] = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        low = text.lower()
        if any(k in low for k in _KEYWORDS):
            matched.append(text)
            total += len(text)
        if total >= _MAX_CHARS:
            break
    return "\n\n".join(matched)[:_MAX_CHARS]


def extract_metrics_via_ai(text: str) -> dict[str, float | None]:
    """Best-effort extraction -- the caller always shows these values to a
    human for review before anything is saved, so a wrong or missing
    number here costs a re-check, not bad data in the platform."""
    empty = {key: None for key in CHARTABLE_METRICS}
    settings = get_settings()
    if not settings.openai_api_key or not text.strip():
        return empty

    client = OpenAI(api_key=settings.openai_api_key)
    metric_lines = "\n".join(f"- {key}: {spec['label']} ({spec['unit']})" for key, spec in CHARTABLE_METRICS.items())
    prompt = (
        "You are extracting sustainability disclosure figures from a company's "
        "BRSR / annual report excerpt below. For each metric listed, find the "
        "reported figure in the EXACT unit given and return it as a plain number. "
        "If a metric is not reported, is reported in a different unit, or you are "
        "not confident, return null for it -- never guess or convert units.\n\n"
        f"Metrics to find:\n{metric_lines}\n\n"
        f"Report excerpt:\n{text}"
    )
    schema = {
        "type": "object",
        "properties": {key: {"type": ["number", "null"]} for key in CHARTABLE_METRICS},
        "required": list(CHARTABLE_METRICS.keys()),
        "additionalProperties": False,
    }
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "peer_metrics", "schema": schema, "strict": True}},
            temperature=0,
        )
        parsed = json.loads(response.choices[0].message.content)
    except Exception:
        return empty
    return {key: parsed.get(key) for key in CHARTABLE_METRICS}
