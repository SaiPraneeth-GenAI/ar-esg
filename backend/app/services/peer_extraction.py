"""BRSR PDF -> peer metric extraction via GPT-4o-mini.

Brute-force by design: the whole document is converted to text
(PyMuPDF, tables extracted as structured rows where detected), split
into fixed-size chunks, and every chunk is sent to the model in
parallel -- nothing is skipped by a keyword or section-detection guess
that might miss the real tables in an unfamiliar report layout. Results
from every chunk are merged (first non-null value found, in page
order, wins per metric). Cost is trivial at gpt-4o-mini pricing even
across a dozen chunks (~$0.01-0.05 for a 300+ page report, measured in
production), and running the chunk calls concurrently keeps wall-clock
time close to one chunk's latency rather than the sum of all of them.
An identical PDF (by content hash) is never re-processed at all -- the
cached result from its first upload is reused.
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


def _format_page(page: "fitz.Page", page_number: int) -> str:
    """Tables as structured pipe-separated rows where detected (keeps a
    dense table's row/column alignment intact, which plain text
    extraction can scramble); the page's full plain text otherwise --
    nothing windowed or trimmed, since the whole point of chunking the
    entire document is not to guess what's relevant."""
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


def _chunk_document(pdf_bytes: bytes) -> tuple[list[str], int]:
    """Every page's text/tables, grouped into chunks of roughly
    _CHARS_PER_CHUNK characters each -- a chunk boundary never splits a
    single page's content. Returns (chunks, total_page_count)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0
    for i, page in enumerate(doc):
        page_text = _format_page(page, i + 1)
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
    return chunks, total_pages


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
        "The text below is one section of a company's BRSR / annual report "
        "(tables are shown as pipe-separated rows where detected). For each "
        "metric listed, find the reported figure in the EXACT unit given and "
        "return it as a plain number. Keep each value aligned with its "
        "correct row/column label -- do not reuse one figure for multiple "
        "metrics. This is only a section of the full report, so most or all "
        "metrics may genuinely not appear here -- if a metric is not present "
        "in THIS text, is reported in a different unit, or you are not "
        "confident, return null for it -- never guess, never convert units, "
        "never invent a value.\n\n"
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

    chunks, total_pages = _chunk_document(pdf_bytes)
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
        "peer_extraction hash=%s elapsed_seconds=%s total_pages=%s chunks=%s billed_chunks=%s timed_out_chunks=%s chars_sent=%s "
        "input_tokens=%s output_tokens=%s total_tokens=%s est_cost_usd=%s found_count=%s/%s",
        doc_hash[:12], elapsed, total_pages, len(chunks), billed_chunks, timed_out_chunks, chars_sent,
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
