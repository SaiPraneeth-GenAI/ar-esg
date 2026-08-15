"""Fully deterministic column/category matching for bulk upload. No AI/LLM
call anywhere in this module -- every suggestion is reproducible (same
input always produces the same output) and explainable (each match carries
the rule that produced it and a similarity score).
"""

import hashlib
import re
from datetime import date

from rapidfuzz import fuzz

from app.core.mapping_aliases import CATEGORY_ALIASES, DATA_POINT_ALIASES, METADATA_FIELD_ALIASES

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

CATEGORY_THRESHOLD = 0.72
METADATA_THRESHOLD = 0.6
DATA_POINT_THRESHOLD = 0.62


def normalize(s: str) -> str:
    return " ".join(s.lower().replace("_", " ").replace("-", " ").split())


class MatchResult:
    def __init__(self, key: str | None, score: float, rule: str):
        self.key = key
        self.score = round(score, 3)
        self.rule = rule


def _best_alias_match(norm: str, candidates: dict[str, list[str]], threshold: float) -> MatchResult:
    for key, aliases in candidates.items():
        if any(normalize(a) == norm for a in [key, *aliases]):
            return MatchResult(key, 1.0, "exact_alias")

    best_key, best_score = None, 0.0
    for key, aliases in candidates.items():
        for alias in [key, *aliases]:
            score = fuzz.token_set_ratio(norm, normalize(alias)) / 100.0
            if score > best_score:
                best_score, best_key = score, key
    if best_score >= threshold:
        return MatchResult(best_key, best_score, "fuzzy")
    return MatchResult(None, best_score, "no_match")


def match_category(candidate: str, category_names: list[str]) -> MatchResult:
    norm = normalize(candidate)
    if not norm:
        return MatchResult(None, 0.0, "no_match")
    aliased = {name: CATEGORY_ALIASES.get(name, []) for name in category_names}
    return _best_alias_match(norm, aliased, CATEGORY_THRESHOLD)


def match_metadata_field(header: str) -> MatchResult:
    norm = normalize(header)
    if not norm:
        return MatchResult(None, 0.0, "no_match")
    return _best_alias_match(norm, METADATA_FIELD_ALIASES, METADATA_THRESHOLD)


def match_data_point(header: str, data_points: list[tuple[str, str]]) -> tuple[MatchResult, str | None]:
    """data_points: list of (id, name). Returns (MatchResult keyed by data point
    id, that id or None)."""
    norm = normalize(header)
    if not norm:
        return MatchResult(None, 0.0, "no_match"), None

    for dp_id, dp_name in data_points:
        aliases = [dp_name, *DATA_POINT_ALIASES.get(dp_name, [])]
        if any(normalize(a) == norm for a in aliases):
            return MatchResult(dp_id, 1.0, "exact_alias"), dp_id

    best_id, best_score = None, 0.0
    for dp_id, dp_name in data_points:
        aliases = [dp_name, *DATA_POINT_ALIASES.get(dp_name, [])]
        for alias in aliases:
            score = fuzz.token_set_ratio(norm, normalize(alias)) / 100.0
            if score > best_score:
                best_score, best_id = score, dp_id
    if best_score >= DATA_POINT_THRESHOLD:
        return MatchResult(best_id, best_score, "fuzzy"), best_id
    return MatchResult(None, best_score, "no_match"), None


def header_fingerprint(headers: list[str]) -> str:
    normalized_sorted = sorted(normalize(h) for h in headers if normalize(h))
    return hashlib.sha256("|".join(normalized_sorted).encode()).hexdigest()


def infer_period(*texts: str) -> date | None:
    """When a sheet has no explicit Period column, try to infer a single
    period for the whole sheet from the sheet name / filename (shown to the
    customer for confirmation, never assumed silently)."""
    for text in texts:
        if not text:
            continue
        low = text.lower()

        m = re.search(r"(\d{4})-(\d{1,2})(?!\d)", low)
        if m:
            month = int(m.group(2))
            if 1 <= month <= 12:
                return date(int(m.group(1)), month, 1)

        m = re.search(r"\b(\d{1,2})[/-](\d{4})\b", low)
        if m:
            month = int(m.group(1))
            if 1 <= month <= 12:
                return date(int(m.group(2)), month, 1)

        for i, name in enumerate(MONTH_NAMES):
            m = re.search(rf"\b{name}[a-z]*[\s_-]?'?(\d{{2,4}})\b", low)
            if m:
                year = int(m.group(1))
                if year < 100:
                    year += 2000
                return date(year, i + 1, 1)

    return None
