"""BRSR PDF -> peer metric extraction via GPT-4o-mini.

Plain PyMuPDF text extraction throughout -- an earlier version also ran
find_tables() per page for cleaner table structure, but that measured at
~1.3s/page on a real annual report (~160x slower than plain text) and was
the actual cause of this pipeline taking minutes; gpt-4o-mini reads a
plain-text table well enough for this use case. A cheap full-document
text pass finds the BRSR section by its real shape -- a cluster of many
section-marker mentions close together, not a single stray reference
elsewhere in the report (a combined annual+BRSR report's cover page or
table of contents will often mention "BRSR" once, which is not the
section itself) -- and only that section's pages are chunked and sent to
the model, concurrently, so wall-clock time stays close to one chunk's
latency rather than the sum of all of them. Cost is trivial at gpt-4o-mini
pricing regardless (~$0.01-0.05 for a 300+ page report, measured in
production). An identical PDF (by content hash) is never re-processed at
all -- the cached result from its first upload is reused.
"""

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF
from openai import OpenAI

from app.api.routes.charts import CHARTABLE_METRICS
from app.core.config import get_settings

logger = logging.getLogger("peer_extraction")

_CHARS_PER_CHUNK = 150_000  # ~35-40k tokens/chunk, comfortably under gpt-4o-mini's context
_MAX_CHUNKS = 14  # safety valve on a pathologically large upload -- ~2.1M chars / a ~500+ page document
# find_tables() (called once per page, unconditionally, to catch dense
# tables) is genuinely slow on a page with real table structure -- across
# a 300+ page annual report full of financial-statement tables, that adds
# up to minutes on this instance's limited CPU, and it all runs BEFORE any
# OpenAI call (and therefore before _CHUNK_TIMEOUT_SECONDS/
# _JOB_TIMEOUT_SECONDS even apply). The old char-budget check in the
# chunking loop below only breaks AFTER a chunk boundary is flushed, so a
# document whose total text stays under _MAX_CHUNKS x _CHARS_PER_CHUNK
# (this one's did) never hit it and every page got scanned regardless.
# This caps pages examined directly, checked BEFORE the expensive call.
_MAX_PAGES_TO_SCAN = 90  # covers a real BRSR section (measured at ~65 pages on a real report) plus buffer -- cheap now that chunking is plain text, not find_tables()
# Fires several chunks at once rather than one at a time -- wall-clock
# time is then close to a batch's latency, not the sum of every chunk.
# Kept well below _MAX_CHUNKS (rather than one worker per chunk) since
# firing all 14 simultaneously on a resource-constrained instance risked
# connection contention that could itself cause the stalls this is meant
# to avoid.
_MAX_WORKERS = 6
_CHUNK_TIMEOUT_SECONDS = 45  # a single chunk call is killed past this, not left to hang the whole job
_JOB_TIMEOUT_SECONDS = 150  # hard ceiling on the whole extraction, in case a chunk somehow ignores its own timeout

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

# BRSR (SEBI's standardized ESG disclosure format) uses fairly consistent
# section terminology across companies. Used only to find WHERE the
# _MAX_PAGES_TO_SCAN budget should start -- in a combined annual+BRSR
# report, the BRSR section is often placed after the financial statements,
# so capping the scan at literally "the first N pages" would reliably miss
# it in exactly the same way the old unfiltered keyword scan did.
_SECTION_ANCHORS = [
    "business responsibility and sustainability report", "brsr",
    "principle 1", "principle 2", "principle 3", "principle 4", "principle 5",
    "principle 6", "principle 7", "principle 8", "principle 9",
    "essential indicators", "leadership indicators",
]


_CLUSTER_GAP_PAGES = 15  # anchor hits within this many pages of each other count as the same section
_CLUSTER_LEAD_IN = 2  # pages of buffer before the detected cluster starts
_CLUSTER_LEAD_OUT = 6  # pages of buffer after the detected cluster ends (a table can spill past the last mention)


def _find_scan_window(page_texts: list[str]) -> tuple[int, int]:
    """Finds the BRSR section by its actual shape: a real section mentions
    "BRSR" / "Principle N" / "Essential Indicators" repeatedly across many
    consecutive pages, not once. A single stray mention (e.g. the cover
    page saying "including our BRSR disclosures") is NOT that shape, so
    picking "the first page that matches" (tried before, and confirmed
    broken against a real report -- it locked onto page 1) is the wrong
    algorithm entirely. This groups every matching page into clusters,
    keeps the largest one (by page count, not span), and returns a window
    around it. Falls back to (0, _MAX_PAGES_TO_SCAN) if nothing matches
    anywhere, so a report with no recognizable markers still gets scanned
    from the start rather than skipped entirely."""
    hit_pages = [i for i, text in enumerate(page_texts) if any(a in text for a in _SECTION_ANCHORS)]
    if not hit_pages:
        return 0, min(len(page_texts), _MAX_PAGES_TO_SCAN)

    clusters: list[list[int]] = [[hit_pages[0]]]
    for p in hit_pages[1:]:
        if p - clusters[-1][-1] <= _CLUSTER_GAP_PAGES:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    best = max(clusters, key=len)

    start = max(0, best[0] - _CLUSTER_LEAD_IN)
    end = min(len(page_texts), best[-1] + _CLUSTER_LEAD_OUT, start + _MAX_PAGES_TO_SCAN)
    return start, end


def _chunk_document(pdf_bytes: bytes) -> tuple[list[str], int, int, int]:
    """Every scanned page's text, grouped into chunks of roughly
    _CHARS_PER_CHUNK characters each -- a chunk boundary never splits a
    single page's content. The _MAX_PAGES_TO_SCAN budget is spent on the
    BRSR section itself (see _find_scan_window), not blindly the first
    pages of the document. Returns (chunks, total_page_count,
    pages_scanned, scan_start_page)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count
    page_texts = [page.get_text() for page in doc]  # cheap: ~3s for a 371-page report, measured
    start, end = _find_scan_window([t.lower() for t in page_texts])

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0
    pages_scanned = 0
    for i in range(start, end):
        page_text = f"--- Page {i + 1} ---\n{page_texts[i]}"
        pages_scanned += 1
        if current_parts and current_len + len(page_text) > _CHARS_PER_CHUNK:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_len = 0
            if len(chunks) >= _MAX_CHUNKS:
                break
        current_parts.append(page_text)
        current_len += len(page_text)
    if current_parts and len(chunks) < _MAX_CHUNKS:
        chunks.append("\n\n".join(current_parts))
    doc.close()
    return chunks, total_pages, pages_scanned, start


def _call_ai(text: str) -> tuple[dict[str, float | None], dict]:
    empty = {key: None for key in CHARTABLE_METRICS}
    settings = get_settings()
    if not settings.openai_api_key or not text.strip():
        return empty, {}

    # No timeout was set anywhere in this pipeline -- a single slow/stuck
    # request (network stall, provider-side slowness) held up the ENTIRE
    # job forever, even when every other chunk had already finished. This
    # bounds a single chunk call, so one straggler can never hang the job.
    client = OpenAI(api_key=settings.openai_api_key, timeout=_CHUNK_TIMEOUT_SECONDS, max_retries=1)
    metric_lines = "\n".join(f"- {key}: {spec['label']} ({spec['unit']})" for key, spec in CHARTABLE_METRICS.items())
    prompt = (
        "The text below is one section of a company's BRSR / annual report, "
        "extracted directly from the PDF (tables may appear as loosely "
        "aligned rows of numbers/labels rather than a clean grid -- read "
        "them by their row/column position in the text, same as you would "
        "looking at the original page). For each metric listed, find the "
        "reported figure in the EXACT unit given and return it as a plain "
        "number. Keep each value aligned with its correct row/column label "
        "-- do not reuse one figure for multiple metrics. This is only a "
        "section of the full report, so most or all metrics may genuinely "
        "not appear here -- if a metric is not present in THIS text, is "
        "reported in a different unit, or you are not confident, return "
        "null for it -- never guess, never convert units, never invent a "
        "value.\n\n"
        f"Metrics to find:\n{metric_lines}\n\n"
        f"Report section:\n{text}"
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
    except Exception as exc:
        logger.warning("peer_extraction chunk AI call failed: %s: %s", type(exc).__name__, exc)
        return empty, {}
    return {key: parsed.get(key) for key in CHARTABLE_METRICS}, usage_stats


def extract_metrics_from_pdf(pdf_bytes: bytes) -> tuple[dict[str, float | None], float]:
    """The single entry point the caller uses: hash -> cache check ->
    whole document chunked -> every chunk sent to the model in parallel
    -> results merged (first non-null value found, in page order, wins
    per metric) -> cache store. Best effort throughout -- the caller
    always shows these values to a human for review before anything is
    saved, so a wrong or missing number here costs a re-check, not bad
    data in the platform. Returns (metrics, elapsed_seconds)."""
    started_at = time.monotonic()
    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()
    cached = _RESULT_CACHE.get(doc_hash)
    if cached is not None:
        elapsed = round(time.monotonic() - started_at, 1)
        logger.info("peer_extraction CACHE_HIT hash=%s elapsed_seconds=%s -- 0 LLM calls", doc_hash[:12], elapsed)
        return cached, elapsed

    chunking_started_at = time.monotonic()
    chunks, total_pages, pages_scanned, scan_start = _chunk_document(pdf_bytes)
    chunking_seconds = round(time.monotonic() - chunking_started_at, 1)
    logger.info(
        "peer_extraction hash=%s CHUNKING_DONE seconds=%s total_pages=%s scan_start_page=%s pages_scanned=%s chunks=%s",
        doc_hash[:12], chunking_seconds, total_pages, scan_start + 1, pages_scanned, len(chunks),
    )
    chars_sent = sum(len(c) for c in chunks)

    merged: dict[str, float | None] = {key: None for key in CHARTABLE_METRICS}
    found_in_chunk: dict[str, int] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    billed_chunks = 0
    timed_out_chunks = 0

    # Each chunk call already has its own _CHUNK_TIMEOUT_SECONDS timeout
    # (set on the OpenAI client itself), so a stalled request fails fast
    # on its own. This is a second, independent backstop: if a future
    # somehow doesn't respect that (e.g. a hang before the request is even
    # sent), the job still returns whatever's been gathered once
    # _JOB_TIMEOUT_SECONDS is up, rather than waiting forever -- Python
    # threads can't be force-killed, so a straggler is simply abandoned
    # (not awaited) rather than blocking the response to the user.
    pool = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
    try:
        futures = {pool.submit(_call_ai, chunk): i for i, chunk in enumerate(chunks)}
        try:
            for future in as_completed(futures, timeout=_JOB_TIMEOUT_SECONDS):
                chunk_index = futures[future]
                extracted, usage = future.result()
                if usage:
                    billed_chunks += 1
                    total_input_tokens += usage.get("input_tokens", 0)
                    total_output_tokens += usage.get("output_tokens", 0)
                for key, value in extracted.items():
                    if value is not None and merged[key] is None:
                        merged[key] = value
                        found_in_chunk[key] = chunk_index
        except TimeoutError:
            timed_out_chunks = sum(1 for f in futures if not f.done())
            logger.warning("peer_extraction job-level timeout hit -- %s chunk(s) abandoned, proceeding with partial results", timed_out_chunks)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    found_count = sum(1 for v in merged.values() if v is not None)
    total_tokens = total_input_tokens + total_output_tokens
    est_cost = round(total_input_tokens / 1_000_000 * _INPUT_COST_PER_M + total_output_tokens / 1_000_000 * _OUTPUT_COST_PER_M, 5)
    elapsed = round(time.monotonic() - started_at, 1)

    logger.info(
        "peer_extraction hash=%s elapsed_seconds=%s chunking_seconds=%s total_pages=%s pages_scanned=%s chunks=%s "
        "billed_chunks=%s timed_out_chunks=%s chars_sent=%s "
        "input_tokens=%s output_tokens=%s total_tokens=%s est_cost_usd=%s found_count=%s/%s",
        doc_hash[:12], elapsed, chunking_seconds, total_pages, pages_scanned, len(chunks),
        billed_chunks, timed_out_chunks, chars_sent,
        total_input_tokens, total_output_tokens, total_tokens, est_cost, found_count, len(merged),
    )

    # Every chunk got a real shot at every metric, so a low count here is
    # much more likely to mean the document genuinely doesn't report most
    # of these figures (or reports them in a different unit) than that the
    # right page was missed -- trust it enough to cache as long as at
    # least one billed call happened.
    if billed_chunks > 0:
        _RESULT_CACHE[doc_hash] = merged
    logger.info("peer_extraction cached=%s", billed_chunks > 0)
    return merged, elapsed


# Back-compat name for callers/tests written against the previous shape.
def extract_metrics_via_ai(text: str) -> dict[str, float | None]:
    extracted, _ = _call_ai(text)
    return extracted
