"""BRSR PDF -> peer metric extraction via GPT-4o-mini.

"Extract everything with code, understand only what's necessary with AI" --
a 300-400 page annual report is handled entirely deterministically first
(PyMuPDF: page-by-page text/table extraction, then a keyword relevance
pass) and only the resulting small excerpt -- typically a few KB across a
couple dozen pages -- ever reaches the LLM. Two further cuts on top of
that: pages with no detected table get only a windowed slice of text
around each keyword hit (not the whole page), and an identical PDF
(by content hash) is never re-sent to the LLM at all -- the cached result
from its first upload is reused. Every call logs page counts, characters
sent, and the actual prompt/completion/total tokens OpenAI reports, so
token usage here is measured, not assumed.
"""

import hashlib
import json
import logging

import fitz  # PyMuPDF
from openai import OpenAI

from app.api.routes.charts import CHARTABLE_METRICS
from app.core.config import get_settings

logger = logging.getLogger("peer_extraction")

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

# These, unlike _KEYWORDS above, are specific enough to BRSR's own section
# structure that they essentially only ever appear INSIDE the BRSR section
# of a combined annual+BRSR report -- generic words like "energy" or
# "revenue" show up throughout a 300+ page annual report's financial
# statements and MD&A long before the BRSR section starts, so scanning for
# ANY keyword hit front-to-back (the old approach) exhausted the page
# budget on false positives without ever reaching the real tables. These
# anchors locate the section itself first.
_SECTION_ANCHORS = [
    "business responsibility and sustainability report", "brsr",
    "principle 1", "principle 2", "principle 3", "principle 4", "principle 5",
    "principle 6", "principle 7", "principle 8", "principle 9",
    "essential indicators", "leadership indicators",
]

_MAX_PAGES = 45  # a real BRSR section usually runs 20-45 pages; cost is trivial (see below) so this is generous on purpose
_MAX_CHARS = 150_000  # ~35-40k tokens worst case, still under $0.01/call at gpt-4o-mini pricing
_WINDOW_RADIUS = 800  # chars of context kept around a keyword hit on pages with no table

# gpt-4o-mini list pricing per 1M tokens, for the estimate in logs only --
# not billed anywhere, purely so "is this actually working" is visible
# without leaving this service.
_INPUT_COST_PER_M = 0.15
_OUTPUT_COST_PER_M = 0.60

# document sha256 -> already-extracted {metric_key: value}. Re-uploading the
# exact same PDF (a common "let me just double check" action) then costs
# zero LLM calls. In-process only, like the extraction job store -- fine
# for this single-instance service, cleared on redeploy.
_RESULT_CACHE: dict[str, dict[str, float | None]] = {}


def _windowed_text(text: str) -> str:
    """Just the context around each keyword hit, not the whole page -- a
    page can be a few thousand characters of prose where only one sentence
    is actually relevant."""
    low = text.lower()
    spans: list[list[int]] = []
    for kw in _KEYWORDS:
        start = 0
        while True:
            idx = low.find(kw, start)
            if idx == -1:
                break
            spans.append([max(0, idx - _WINDOW_RADIUS), min(len(text), idx + len(kw) + _WINDOW_RADIUS)])
            start = idx + len(kw)
    if not spans:
        return text[:2000]
    spans.sort()
    merged: list[list[int]] = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return "\n[...]\n".join(text[s:e] for s, e in merged)


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
        parts.append(_windowed_text(page.get_text()))

    return "\n".join(parts)


def _page_texts(doc: "fitz.Document") -> list[str]:
    return [page.get_text().lower() for page in doc]


def _select_page_indices(page_texts: list[str]) -> tuple[list[int], str]:
    """Picks which pages to send, in three tiers:
    1. A real BRSR section, if one exists -- found via section-specific
       anchors (not generic keywords, which false-positive throughout a
       long annual report's financial sections). The section is
       contiguous by construction (first anchor hit to last, +3 pages of
       buffer for a table that spills past the final mention), so this is
       the whole section, not a handful of scattered pages.
    2. Otherwise, any page matching the broader keyword list, scanning the
       WHOLE document (not stopping at the first _MAX_PAGES hits) so a
       relevant page late in the document isn't dropped in favor of an
       early false positive -- capped to _MAX_PAGES afterward.
    3. Otherwise, the first _MAX_PAGES pages, so the model sees something
       rather than nothing.
    Returns (indices, mode) where mode is "section" | "keyword" | "fallback".
    """
    anchor_pages = [i for i, text in enumerate(page_texts) if any(a in text for a in _SECTION_ANCHORS)]
    if anchor_pages:
        start, end = anchor_pages[0], min(anchor_pages[-1] + 3, len(page_texts) - 1)
        return list(range(start, end + 1))[:_MAX_PAGES], "section"

    keyword_pages = [i for i, text in enumerate(page_texts) if any(k in text for k in _KEYWORDS)]
    if keyword_pages:
        return keyword_pages[:_MAX_PAGES], "keyword"

    return list(range(min(_MAX_PAGES, len(page_texts)))), "fallback"


def extract_relevant_text(pdf_bytes: bytes) -> tuple[str, dict]:
    """Text (tables extracted as structured rows where detected, windowed
    text otherwise) for the selected pages -- see _select_page_indices for
    how those are chosen. Returns (text, stats)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count
    page_texts = _page_texts(doc)
    indices, mode = _select_page_indices(page_texts)

    chunks: list[str] = []
    total = 0
    pages_sent = 0
    for i in indices:
        chunk = _format_page(doc[i], i + 1)
        chunks.append(chunk)
        total += len(chunk)
        pages_sent += 1
        if total >= _MAX_CHARS:
            break
    doc.close()

    text = "\n\n".join(chunks)[:_MAX_CHARS]
    stats = {
        "total_pages": total_pages,
        "candidate_pages": len(indices),
        "pages_sent": pages_sent,
        "chars_sent": len(text),
        "selection_mode": mode,
        "used_fallback": mode == "fallback",
    }
    return text, stats


def _call_ai(text: str) -> tuple[dict[str, float | None], dict]:
    empty = {key: None for key in CHARTABLE_METRICS}
    settings = get_settings()
    if not settings.openai_api_key or not text.strip():
        return empty, {}

    client = OpenAI(api_key=settings.openai_api_key)
    metric_lines = "\n".join(f"- {key}: {spec['label']} ({spec['unit']})" for key, spec in CHARTABLE_METRICS.items())
    prompt = (
        "The text below was extracted from a company's BRSR / annual report "
        "(tables are shown as pipe-separated rows where detected; other "
        "sections are windowed excerpts around relevant terms, not full "
        "pages). For each metric listed, find the reported figure in the "
        "EXACT unit given and return it as a plain number. Keep each value "
        "aligned with its correct row/column label -- do not reuse one "
        "figure for multiple metrics. If a metric is not present in this "
        "text, is reported in a different unit, or you are not confident, "
        "return null for it -- never guess, never convert units, never "
        "invent a value.\n\n"
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
        usage = response.usage
        usage_stats = (
            {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens, "total_tokens": usage.total_tokens}
            if usage
            else {}
        )
    except Exception:
        logger.exception("peer_extraction AI call failed")
        return empty, {}
    return {key: parsed.get(key) for key in CHARTABLE_METRICS}, usage_stats


def extract_metrics_from_pdf(pdf_bytes: bytes) -> dict[str, float | None]:
    """The single entry point the caller uses: hash -> cache check ->
    deterministic extraction -> LLM (only if needed) -> cache store. Best
    effort throughout -- the caller always shows these values to a human
    for review before anything is saved, so a wrong or missing number
    here costs a re-check, not bad data in the platform."""
    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()
    cached = _RESULT_CACHE.get(doc_hash)
    if cached is not None:
        logger.info("peer_extraction CACHE_HIT hash=%s -- 0 LLM calls", doc_hash[:12])
        return cached

    text, stats = extract_relevant_text(pdf_bytes)
    extracted, usage = _call_ai(text)

    est_cost = None
    if usage:
        est_cost = round(
            usage["input_tokens"] / 1_000_000 * _INPUT_COST_PER_M + usage["output_tokens"] / 1_000_000 * _OUTPUT_COST_PER_M, 5
        )

    found_count = sum(1 for v in extracted.values() if v is not None)
    logger.info(
        "peer_extraction mode=%s hash=%s total_pages=%s candidate_pages=%s pages_sent=%s chars_sent=%s "
        "est_input_tokens=%s actual_input_tokens=%s output_tokens=%s total_tokens=%s est_cost_usd=%s found_count=%s/%s",
        stats.get("selection_mode"),
        doc_hash[:12],
        stats.get("total_pages"),
        stats.get("candidate_pages"),
        stats.get("pages_sent"),
        stats.get("chars_sent"),
        round(stats.get("chars_sent", 0) / 4),  # rough chars-per-token estimate, for comparison with the actual figure next to it
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        usage.get("total_tokens"),
        est_cost,
        found_count,
        len(extracted),
    )

    # A billed call that found only a couple of values is more likely a
    # fluke -- the right pages weren't quite selected -- than proof the
    # document really only reports 1-2 of these metrics. Caching it would
    # make that weak result permanent for every re-upload of this exact
    # file until the next deploy, so only a call that found a meaningful
    # share is trusted enough to skip re-running next time.
    should_cache = bool(usage) and found_count >= max(4, len(extracted) // 4)
    if should_cache:
        _RESULT_CACHE[doc_hash] = extracted
    logger.info("peer_extraction cached=%s", should_cache)
    return extracted


# Back-compat names for callers/tests written against the previous shape.
def extract_metrics_via_ai(text: str) -> dict[str, float | None]:
    extracted, _ = _call_ai(text)
    return extracted
