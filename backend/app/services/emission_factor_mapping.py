"""Deterministic parsing for the Emission Factors bulk upload. No AI/LLM
anywhere in this -- built on top of app/services/mapping.py's alias +
fuzzy-match engine (Prompt 3d), extended for what a real GHG inventory
workbook actually looks like:

- Multiple tables can sit in one sheet (a main factor table plus a smaller
  one further down, separated by a blank row) -- `split_into_blocks`.
- A factor's value can live in a year-suffixed column ("Emission Factor
  FY25") that needs pivoting into its own versioned row, rather than a
  fixed column -- `detect_year_token` + `classify_columns`.
- A factor's value can be embedded in unstructured text spanning two years
  in one cell ("0.727 for FY25 & 0.710 for FY26") -- `parse_embedded_year_values`.
- The same sheet mixes factor columns with consumption/output columns that
  must never be imported as factors -- the "factor" keyword takes priority
  over consumption/emission keywords when a year-tagged column is seen.
"""

import re
from datetime import date

from rapidfuzz import fuzz

from app.core.emission_factor_aliases import (
    DERIVED_COLUMN_KEYWORDS,
    EMISSION_FACTOR_FIELD_ALIASES,
    FACTOR_YEAR_KEYWORDS,
    NON_FACTOR_YEAR_KEYWORDS,
    SCOPE3_CATEGORY_ALIASES,
    SCOPE_SHEET_ALIASES,
)
from app.services.mapping import MatchResult, best_alias_match, normalize

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTH_ABBREV = {m[:3]: i + 1 for i, m in enumerate(MONTH_NAMES)}

SCOPE_THRESHOLD = 0.7
FIELD_THRESHOLD = 0.6


def match_scope(*texts: str) -> MatchResult:
    """Tries the sheet name first, then the filename -- same fallback order
    as entries bulk-upload's category detection."""
    for text in texts:
        norm = normalize(text or "")
        if not norm:
            continue
        result = best_alias_match(norm, SCOPE_SHEET_ALIASES, SCOPE_THRESHOLD)
        if result.key:
            return result
    return MatchResult(None, 0.0, "no_match")


class YearToken:
    def __init__(self, version_label: str, effective_date: date):
        self.version_label = version_label
        self.effective_date = effective_date


def detect_year_token(header: str) -> YearToken | None:
    """Pulls a version/year label out of a column header. Handles plain
    fiscal years (FY25, FY 2026), bare years (2025), and dated publication
    labels (IPCC Feb 2024, IPCC Aug 2024) -- the same mechanism covers both
    the FY25/FY26 wide-year-column case and the refrigerant GWP
    publication-date sub-table, since both are just year/version-tagged
    columns."""
    if not header:
        return None
    low = header.lower()

    # "IPCC Feb 2024" / "Feb 2024" / "February 2024"
    for abbrev, month_num in MONTH_ABBREV.items():
        m = re.search(rf"\b({abbrev}[a-z]*)[\s.-]+(\d{{4}})\b", low)
        if m:
            year = int(m.group(2))
            prefix = "IPCC " if "ipcc" in low else ""
            month_name = m.group(1).capitalize()
            return YearToken(f"{prefix}{month_name} {year}".strip(), date(year, month_num, 1))

    # "FY25" / "FY 2025" / "FY-26"
    m = re.search(r"\bfy[\s-]?(\d{2,4})\b", low)
    if m:
        raw = m.group(1)
        year = int(raw) if len(raw) == 4 else 2000 + int(raw)
        short = raw if len(raw) == 2 else str(year)[2:]
        return YearToken(f"FY{short}", date(year, 1, 1))

    # bare 4-digit year, e.g. a lone "2023" column header
    m = re.search(r"\b(20\d{2})\b", low)
    if m:
        year = int(m.group(1))
        return YearToken(str(year), date(year, 1, 1))

    return None


def is_factor_year_column(header: str) -> bool:
    """Given a header that already carries a year token, decides whether
    it's the factor itself or the consumption/output column sitting next to
    it in the same real-world sheet. "factor" always wins if present."""
    norm = normalize(header)
    if any(kw in norm for kw in FACTOR_YEAR_KEYWORDS):
        return True
    if any(kw in norm for kw in NON_FACTOR_YEAR_KEYWORDS):
        return False
    # No specific keyword either way (e.g. a bare "FY25" header with no
    # other qualifier) -- treat as a factor column, since that's what a
    # year-only header means on a dedicated factor sheet.
    return True


class ColumnRole:
    def __init__(self, role: str, score: float, rule: str, year_token: YearToken | None = None):
        self.role = role
        self.score = score
        self.rule = rule
        self.year_token = year_token


UNIQUE_ROLES = {"name", "method", "scope3_category", "description", "unit", "source", "source_reference", "value"}


def classify_columns(headers: list[str]) -> list[ColumnRole]:
    """One role per header. Year-tagged headers are detected first (any
    number of these are allowed -- each pivots into its own row later).
    Everything else is matched against the field alias dictionary; if two
    headers would claim the same single-instance role, only the
    higher-scoring one keeps it and the rest fall back to unmatched (which
    renders as "Skip" and is always overridable)."""
    provisional: list[ColumnRole] = []
    for header in headers:
        norm_check = normalize(header)
        if any(kw in norm_check for kw in DERIVED_COLUMN_KEYWORDS):
            provisional.append(ColumnRole("skip", 1.0, "derived_column"))
            continue

        year_token = detect_year_token(header)
        if year_token is not None:
            if is_factor_year_column(header):
                provisional.append(ColumnRole("year_value", 0.9, "year_token", year_token))
            else:
                provisional.append(ColumnRole("skip", 0.9, "year_token_non_factor", year_token))
            continue

        norm = normalize(header)
        if not norm:
            provisional.append(ColumnRole("skip", 0.0, "blank_header"))
            continue

        match = best_alias_match(norm, EMISSION_FACTOR_FIELD_ALIASES, FIELD_THRESHOLD)
        if match.key:
            provisional.append(ColumnRole(match.key, match.score, match.rule))
        else:
            provisional.append(ColumnRole("skip", match.score, "no_match"))

    best_per_role: dict[str, int] = {}
    for i, col in enumerate(provisional):
        if col.role in UNIQUE_ROLES:
            current_best = best_per_role.get(col.role)
            if current_best is None or col.score > provisional[current_best].score:
                best_per_role[col.role] = i

    claimed_indices = set(best_per_role.values())
    for i, col in enumerate(provisional):
        if col.role in UNIQUE_ROLES and i not in claimed_indices:
            provisional[i] = ColumnRole("skip", col.score, "duplicate_demoted")

    return provisional


EMBEDDED_PAIR_RE = re.compile(
    r"([\d.]+)\s*(?:for|@|in)?\s*(fy\s?\d{2,4}|20\d{2})",
    re.IGNORECASE,
)


def parse_embedded_year_values(text: str) -> list[tuple[str, date]] | None:
    """Parses a cell like "0.727 for FY25 & 0.710 for FY26" into
    [("FY25", 0.727, date(2025,1,1)), ("FY26", 0.710, date(2026,1,1))].
    Returns None (never a guess) if the text doesn't confidently match --
    the caller flags the row for manual confirmation instead."""
    if not text:
        return None
    matches = list(EMBEDDED_PAIR_RE.finditer(text))
    if len(matches) < 2:
        return None

    # Sanity check: every number-looking token in the string should fall
    # inside a matched pair's value or year span -- if there's a stray
    # number we didn't attach to a year, don't silently drop it, bail out
    # and ask a human. (A plain [\d.]+ scan over the raw text would also
    # "find" the digits inside "FY25" itself, so this checks position
    # against the matched spans rather than just counting occurrences.)
    consumed_spans = [span for m in matches for span in (m.span(1), m.span(2))]

    def is_consumed(pos: int) -> bool:
        return any(start <= pos < end for start, end in consumed_spans)

    for num_match in re.finditer(r"[\d.]+", text):
        if not is_consumed(num_match.start()):
            return None

    results: list[tuple[str, float, date]] = []
    for m in matches:
        value_str, year_str = m.group(1), m.group(2)
        try:
            value = float(value_str)
        except ValueError:
            return None
        token = detect_year_token(year_str)
        if token is None:
            return None
        results.append((token.version_label, value, token.effective_date))

    return results


def split_into_blocks(rows: list[list[str]]) -> list[tuple[int, list[str], list[list[str]]]]:
    """Splits a sheet's raw rows into independent tables wherever a fully
    blank row separates them -- e.g. a Scope-1 sheet with a small
    refrigerant-GWP table further down, under its own header row. Returns
    (start_row_index, headers, data_rows) per block; blocks with fewer than
    1 data row are dropped."""
    blocks: list[tuple[int, list[str], list[list[str]]]] = []
    current: list[list[str]] = []
    current_start = 0

    def is_blank(row: list[str]) -> bool:
        return all(not str(c).strip() for c in row)

    def flush(start_idx: int, block_rows: list[list[str]]) -> None:
        if len(block_rows) < 2:
            return
        headers = [str(c).strip() for c in block_rows[0]]
        data_rows = block_rows[1:]
        if not any(h for h in headers):
            return
        blocks.append((start_idx, headers, data_rows))

    for i, row in enumerate(rows):
        if is_blank(row):
            if current:
                flush(current_start, current)
                current = []
            continue
        if not current:
            current_start = i
        current.append(row)

    if current:
        flush(current_start, current)

    return blocks
