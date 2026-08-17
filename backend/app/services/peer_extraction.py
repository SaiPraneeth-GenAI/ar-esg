"""BRSR PDF -> peer metric extraction via GPT-4o-mini.

Plain-text extraction (pypdf/pdfplumber) scrambles table layout on the
dense multi-column tables BRSR reports use for GHG/intensity/safety
figures -- numbers end up detached from their row labels, so the model
ends up guessing. Instead this renders just the pages that look relevant
as IMAGES (via PyMuPDF) and sends those to a vision-capable model, the
same way a human reading the PDF (or "upload this to ChatGPT") would --
the table structure stays intact. A 100+ page annual report only has a
handful of pages with these figures, so page selection by keyword keeps
the number of images (and therefore the cost) small.
"""

import base64
import io
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

_MAX_PAGES = 8  # this service runs on a 512MB instance -- each rendered
# page is held in memory simultaneously (they all go in one vision call),
# so this and _RENDER_DPI directly trade off against an OOM kill.
_RENDER_DPI = 110


def select_relevant_pages(pdf_bytes: bytes) -> list[bytes]:
    """PNG bytes for up to _MAX_PAGES pages whose text mentions a
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

    images: list[bytes] = []
    matrix = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)
    for i in indices:
        pix = doc[i].get_pixmap(matrix=matrix)
        images.append(pix.tobytes("png"))
        pix = None  # release before rendering the next page
    doc.close()
    return images


def extract_metrics_via_ai(page_images: list[bytes]) -> dict[str, float | None]:
    """Best-effort extraction -- the caller always shows these values to a
    human for review before anything is saved, so a wrong or missing
    number here costs a re-check, not bad data in the platform."""
    empty = {key: None for key in CHARTABLE_METRICS}
    settings = get_settings()
    if not settings.openai_api_key or not page_images:
        return empty

    client = OpenAI(api_key=settings.openai_api_key)
    metric_lines = "\n".join(f"- {key}: {spec['label']} ({spec['unit']})" for key, spec in CHARTABLE_METRICS.items())
    prompt = (
        "These images are pages from a company's BRSR / annual report. For each "
        "metric listed below, find the reported figure in the EXACT unit given "
        "and return it as a plain number. Read any tables carefully, keeping "
        "each value aligned with its correct row/column label -- do not reuse "
        "one figure for multiple metrics. If a metric is not shown in these "
        "pages, is reported in a different unit, or you are not confident, "
        "return null for it -- never guess, never convert units, never invent "
        "a value.\n\n"
        f"Metrics to find:\n{metric_lines}"
    )
    content: list[dict] = [{"type": "text", "text": prompt}]
    for img in page_images:
        b64 = base64.b64encode(img).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "auto"}})

    schema = {
        "type": "object",
        "properties": {key: {"type": ["number", "null"]} for key in CHARTABLE_METRICS},
        "required": list(CHARTABLE_METRICS.keys()),
        "additionalProperties": False,
    }
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {"name": "peer_metrics", "schema": schema, "strict": True}},
            temperature=0,
        )
        parsed = json.loads(response.choices[0].message.content)
    except Exception:
        return empty
    return {key: parsed.get(key) for key in CHARTABLE_METRICS}
