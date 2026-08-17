"""BRSR PDF -> peer metric extraction via GPT-4o-mini.

Naive plain-text extraction (pypdf, or PyMuPDF's default get_text()) can
scramble a dense multi-column table's layout -- numbers end up detached
from their row labels. Rather than fall back to sending page IMAGES to a
vision model (more expensive, slower, and memory-heavy -- a real problem
on this service's small instance), this uses PyMuPDF's table finder to
extract each relevant page's tables as structured rows/columns first,
falling back to plain text only for pages with no detected table. That
keeps the AI's job easy (a few KB of clean text, table structure intact)
without the cost or memory footprint of images. A 100+ page annual report
only has a handful of pages with these figures, so page selection by
keyword keeps what's sent small regardless.
"""

import json

import fitz  # PyMuPDF
from openai import OpenAI

from app.api.routes.charts import CHARTABLE_METRICS
from app.core.config import get_settings

# BRSR (SEBI's standardized ESG disclosure format) uses fairly consistent
# section/terminology across companies, so these catch the pages that
# matter without needing every company's report to phrase things the same
# way a generic "ghg"/"water" keyword list would require.
_KEYWORDS = [
    "scope 1", "scope 2", "scope i", "scope ii", "scope-1", "scope-2",
    "ghg", "greenhouse gas", "co2", "co2e", "tco2",
    "energy consum", "energy intensity", "water consum", "water withdraw", "water intensity",
    "waste generat", "waste intensity", "hazardous waste",
    "fatalit", "ltifr", "lost time injury", "lost-time injury",
    "driving training", "unsafe condition", "near miss", "safety incident",
    "brsr", "intensity", "turnover", "revenue", "principle 6", "principle 3",
    "essential indicators", "employee well-being", "environment",
]

_MAX_PAGES = 20  # plain text is cheap -- no memory pressure like page images had
_MAX_CHARS = 50_000  # ~12-13k tokens, still a small, fast, cheap gpt-4o-mini call


def _format_page(page: "fitz.Page", page_number: int) -> str:
    parts = [f"--- Page {page_number} ---"]
    try:
        tables = page.find_tables()
    except Exception:
        tables = None

    found_table = False
    if tables is not None:
        for table in tables:
            rows = table.extract()
            if not rows:
                continue
            found_table = True
            for row in rows:
                parts.append(" | ".join((str(cell).strip() if cell is not None else "") for cell in row))

    if not found_table:
        parts.append(page.get_text())

    return "\n".join(parts)


def extract_relevant_text(pdf_bytes: bytes) -> str:
    """Text (tables extracted as structured rows where detected, plain
    text otherwise) for up to _MAX_PAGES pages whose text mentions a
    BRSR/ESG-relevant term. Falls back to the first _MAX_PAGES pages if
    nothing matches (better to show the model something than nothing)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    matched_indices: list[int] = []
    for i, page in enumerate(doc):
        text = page.get_text().lower()
        if any(k in text for k in _KEYWORDS):
            matched_indices.append(i)
        if len(matched_indices) >= _MAX_PAGES:
            break

    indices = matched_indices if matched_indices else list(range(min(_MAX_PAGES, doc.page_count)))

    chunks: list[str] = []
    total = 0
    for i in indices:
        chunk = _format_page(doc[i], i + 1)
        chunks.append(chunk)
        total += len(chunk)
        if total >= _MAX_CHARS:
            break
    doc.close()
    return "\n\n".join(chunks)[:_MAX_CHARS]


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
        "The text below was extracted from a company's BRSR / annual report "
        "(tables are shown as pipe-separated rows where detected). For each "
        "metric listed, find the reported figure in the EXACT unit given and "
        "return it as a plain number. Keep each value aligned with its correct "
        "row/column label -- do not reuse one figure for multiple metrics. If a "
        "metric is not present in this text, is reported in a different unit, "
        "or you are not confident, return null for it -- never guess, never "
        "convert units, never invent a value.\n\n"
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
