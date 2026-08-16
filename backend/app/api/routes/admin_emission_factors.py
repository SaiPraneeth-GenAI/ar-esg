from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from rapidfuzz import fuzz

from app.core.auth import CurrentUser, require_roles
from app.core.emission_factor_aliases import SCOPE3_CATEGORY_ALIASES
from app.db.models import EmissionFactor, IpccReference
from app.db.session import get_db
from app.schemas.emission_factors import (
    EFBulkImportRequest,
    EFBulkImportResponse,
    EFBulkImportResult,
    EFColumnSuggestion,
    EFDetectRequest,
    EFDetectResponse,
    EFFactorDraft,
    EFSheetDetectionResult,
    EmissionFactorCreate,
    EmissionFactorOut,
    IpccMatch,
    IpccSearchResult,
    IpccVersionOut,
)
from app.services.emission_factor_mapping import (
    UNIQUE_ROLES,
    ColumnRole,
    classify_columns,
    match_scope,
    normalize,
    parse_embedded_year_values,
    split_into_blocks,
)
from app.services.mapping import best_alias_match

router = APIRouter(prefix="/admin/emission-factors", tags=["admin"])


def _out(f: EmissionFactor) -> EmissionFactorOut:
    return EmissionFactorOut(
        id=f.id,
        scope=f.scope,
        gas_type=f.gas_type,
        method=f.method,
        scope3_category=f.scope3_category,
        description=f.description,
        unit=f.unit,
        factor_value=float(f.factor_value),
        effective_year=f.effective_date.year,
        version=f.version,
        source=f.source,
        source_reference=f.source_reference,
        ipcc_reference_key=f.ipcc_reference_key,
    )


@router.get("", response_model=list[EmissionFactorOut])
def list_factors(
    scope: int | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    q = db.query(EmissionFactor).filter(EmissionFactor.tenant_id == current.tenant_id)
    if scope is not None:
        q = q.filter(EmissionFactor.scope == scope)
    rows = q.order_by(EmissionFactor.scope, EmissionFactor.effective_date.desc()).all()
    return [_out(r) for r in rows]


@router.post("", response_model=EmissionFactorOut, status_code=201)
def create_factor(
    payload: EmissionFactorCreate,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    factor = EmissionFactor(
        tenant_id=current.tenant_id,
        scope=payload.scope,
        gas_type=payload.gas_type,
        method=payload.method,
        scope3_category=payload.scope3_category,
        description=payload.description,
        unit=payload.unit,
        factor_value=payload.factor_value,
        effective_date=date(payload.effective_year, 1, 1),
        version=f"FY{str(payload.effective_year)[2:]}",
        source=payload.source,
        source_reference=payload.source_reference,
        ipcc_reference_key=payload.ipcc_reference_key,
    )
    db.add(factor)
    db.commit()
    db.refresh(factor)
    return _out(factor)


# ---- IPCC reference (seeded, read-only) ------------------------------------


def _search_score(query_norm: str, candidates: list[str]) -> tuple[float, str]:
    for c in candidates:
        if normalize(c).startswith(query_norm):
            return 1.0, "prefix"

    q_tokens = query_norm.split()
    if q_tokens:
        for c in candidates:
            c_tokens = normalize(c).split()
            if all(any(ct.startswith(qt) for ct in c_tokens) for qt in q_tokens):
                return 0.92, "word_match"

    best = 0.0
    for c in candidates:
        best = max(best, fuzz.token_set_ratio(query_norm, normalize(c)) / 100.0)
    return best, "fuzzy"


@router.get("/ipcc-reference/search", response_model=list[IpccSearchResult])
def search_ipcc_reference(
    q: str,
    scope: int | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    """Prefix-first, then word-by-word, then fuzzy fallback -- against both
    substance_name and aliases. No AI/LLM. Returns up to 8 substances,
    newest version's year/publication attached for display."""
    query_norm = normalize(q)
    if not query_norm:
        return []

    query = db.query(IpccReference)
    if scope is not None:
        query = query.filter(IpccReference.scope == scope)
    rows = query.all()

    by_substance: dict[str, list[IpccReference]] = {}
    for row in rows:
        by_substance.setdefault(row.substance_name, []).append(row)

    scored: list[tuple[float, str, IpccReference]] = []
    for substance_name, versions in by_substance.items():
        aliases = versions[0].aliases or []
        score, _rule = _search_score(query_norm, [substance_name, *aliases])
        if score >= 0.45:
            latest = max(versions, key=lambda v: v.effective_year)
            scored.append((score, substance_name, latest))

    scored.sort(key=lambda t: (-t[0], t[1]))
    return [
        IpccSearchResult(
            substance_name=name,
            scope=latest.scope,
            factor_type=latest.factor_type,
            latest_effective_year=latest.effective_year,
            latest_publication=latest.publication,
        )
        for _score, name, latest in scored[:8]
    ]


@router.get("/ipcc-reference/versions", response_model=list[IpccVersionOut])
def list_ipcc_versions(
    substance_name: str,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    """Every published version for this substance, newest first -- this is
    what makes a historical year's factor available (e.g. backdating a
    FY2022 entry to the IPCC AR5 GWP that was current then)."""
    rows = (
        db.query(IpccReference)
        .filter(IpccReference.substance_name == substance_name)
        .order_by(IpccReference.effective_year.desc())
        .all()
    )
    return [
        IpccVersionOut(
            id=r.id,
            substance_name=r.substance_name,
            scope=r.scope,
            factor_type=r.factor_type,
            publication=r.publication,
            effective_year=r.effective_year,
            ncv_mj_per_unit=float(r.ncv_mj_per_unit) if r.ncv_mj_per_unit is not None else None,
            density_kg_per_unit=float(r.density_kg_per_unit) if r.density_kg_per_unit is not None else None,
            co2_ef_per_tj=float(r.co2_ef_per_tj) if r.co2_ef_per_tj is not None else None,
            oxidation_factor=float(r.oxidation_factor) if r.oxidation_factor is not None else None,
            derived_factor_value=float(r.derived_factor_value),
            unit=r.unit,
            source_reference=r.source_reference,
        )
        for r in rows
    ]


def _find_ipcc_match(name: str | None, scope: int, all_refs: list[IpccReference]) -> IpccMatch | None:
    """Best-effort, informational only -- used to show the bulk-upload
    cross-reference comparison. Never adjusts the uploaded value."""
    if not name:
        return None
    query_norm = normalize(name)
    if not query_norm:
        return None

    by_substance: dict[str, list[IpccReference]] = {}
    for row in all_refs:
        if row.scope == scope:
            by_substance.setdefault(row.substance_name, []).append(row)

    best_score, best_substance = 0.0, None
    for substance_name, versions in by_substance.items():
        aliases = versions[0].aliases or []
        score, _rule = _search_score(query_norm, [substance_name, *aliases])
        if score > best_score:
            best_score, best_substance = score, substance_name

    if best_substance is None or best_score < 0.6:
        return None

    latest = max(by_substance[best_substance], key=lambda v: v.effective_year)
    return IpccMatch(
        substance_name=latest.substance_name,
        publication=latest.publication,
        effective_year=latest.effective_year,
        reference_value=float(latest.derived_factor_value),
        unit=latest.unit,
        delta_pct=None,  # filled in per-row once the uploaded value is known
    )


def _canonical_scope3_category(raw: str) -> str:
    norm = normalize(raw)
    if not norm:
        return raw
    match = best_alias_match(norm, SCOPE3_CATEGORY_ALIASES, 0.6)
    return match.key if match.key else raw


def _cell(row: list[str], idx: int) -> str:
    return row[idx].strip() if idx < len(row) and row[idx] is not None else ""


@router.post("/bulk-detect", response_model=EFDetectResponse)
def bulk_detect(
    payload: EFDetectRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    """Fully deterministic, no AI/LLM. Per sheet: splits on blank rows into
    independent tables (a main factor table plus a smaller one further
    down share one sheet in the real workbook), guesses the GHG scope from
    the sheet name, classifies every column (a fixed metadata field, a
    year-tagged factor value to pivot, or skip), then pivots each data row
    into one EFFactorDraft per year/version column -- or per (year, value)
    pair extracted from a combined-text cell. Each row is also cross-checked
    against the seeded IPCC/CEA/DEFRA reference table, purely informational
    -- it never overwrites the uploaded value."""
    all_refs = db.query(IpccReference).all()
    results: list[EFSheetDetectionResult] = []

    for sheet in payload.sheets:
        scope_match = match_scope(sheet.name, sheet.filename)
        scope = int(scope_match.key) if scope_match.key else None

        blocks = split_into_blocks([sheet.headers, *sheet.rows]) if sheet.rows else split_into_blocks([sheet.headers])
        if not blocks:
            continue

        for block_index, (block_start, headers, data_rows) in enumerate(blocks):
            col_roles = classify_columns(headers)

            for i in range(len(headers)):
                override = (sheet.column_overrides or {}).get(f"{block_index}:{i}")
                if override:
                    year_token = col_roles[i].year_token if override == "year_value" else None
                    col_roles[i] = ColumnRole(override, 1.0, "manual_override", year_token)

            claimed: dict[str, int] = {}
            for i, col in enumerate(col_roles):
                if col.role in UNIQUE_ROLES:
                    current_claim = claimed.get(col.role)
                    if current_claim is None or col.score > col_roles[current_claim].score:
                        claimed[col.role] = i
            keep = set(claimed.values())
            for i, col in enumerate(col_roles):
                if col.role in UNIQUE_ROLES and i not in keep:
                    col_roles[i] = ColumnRole("skip", col.score, "duplicate_demoted")

            columns = [
                EFColumnSuggestion(
                    header=headers[i],
                    index=i,
                    role=col_roles[i].role,
                    year_label=col_roles[i].year_token.version_label if col_roles[i].year_token else None,
                    score=col_roles[i].score,
                    rule=col_roles[i].rule,
                )
                for i in range(len(headers))
            ]

            role_index: dict[str, int] = {}
            year_cols: list[tuple[int, str, date]] = []
            for i, col in enumerate(col_roles):
                if col.role == "year_value" and col.year_token:
                    year_cols.append((i, col.year_token.version_label, col.year_token.effective_date))
                elif col.role in ("name", "method", "scope3_category", "description", "unit", "source", "source_reference", "value"):
                    role_index[col.role] = i

            factors: list[EFFactorDraft] = []
            for r, row in enumerate(data_rows):
                if all(not _cell(row, i) for i in range(len(row))):
                    continue

                gas_type = _cell(row, role_index["name"]) if "name" in role_index else None
                method = _cell(row, role_index["method"]) if "method" in role_index else None
                scope3_category_raw = _cell(row, role_index["scope3_category"]) if "scope3_category" in role_index else None
                scope3_category = _canonical_scope3_category(scope3_category_raw) if scope3_category_raw else None
                description = _cell(row, role_index["description"]) if "description" in role_index else None
                unit = _cell(row, role_index["unit"]) if "unit" in role_index else None
                source = _cell(row, role_index["source"]) if "source" in role_index else None
                source_reference = _cell(row, role_index["source_reference"]) if "source_reference" in role_index else None

                if (scope or 1) == 2 and not method and payload.default_method:
                    method = payload.default_method

                common = dict(
                    sheet_name=sheet.name,
                    block_index=block_index,
                    scope=scope or 1,
                    gas_type=gas_type or None,
                    method=method or None,
                    scope3_category=scope3_category or None,
                    description=description or None,
                    unit=unit or None,
                    source=source or None,
                    source_reference=source_reference or None,
                )

                pivots: list[tuple[str, float | None, date | None, str | None, str | None]] = []
                # (version_label, value, effective_date, status_override, raw_text)

                if year_cols:
                    for col_i, version_label, eff_date in year_cols:
                        raw_text = _cell(row, col_i)
                        if not raw_text:
                            continue
                        try:
                            value = float(raw_text)
                            pivots.append((version_label, value, eff_date, None, None))
                        except ValueError:
                            embedded = parse_embedded_year_values(raw_text)
                            if embedded:
                                for lbl, val, edate in embedded:
                                    pivots.append((lbl, val, edate, None, raw_text))
                            else:
                                pivots.append((version_label, None, eff_date, "needs_confirmation", raw_text))
                elif "value" in role_index:
                    raw_text = _cell(row, role_index["value"])
                    if raw_text:
                        try:
                            value = float(raw_text)
                            fallback_year = payload.default_effective_year or date.today().year
                            pivots.append((f"FY{str(fallback_year)[2:]}", value, date(fallback_year, 1, 1), None, None))
                        except ValueError:
                            embedded = parse_embedded_year_values(raw_text)
                            if embedded:
                                for lbl, val, edate in embedded:
                                    pivots.append((lbl, val, edate, None, raw_text))
                            else:
                                pivots.append((None, None, None, "needs_confirmation", raw_text))

                for version_label, value, eff_date, status_override, raw_text in pivots:
                    status = status_override or "ready"
                    message = None
                    if status_override == "needs_confirmation":
                        message = "Could not read a clean number for this cell -- edit the value directly."
                    elif not unit:
                        status, message = "needs_confirmation", "No unit found for this row."
                    elif not source_reference:
                        status, message = "missing_source", "No source reference -- required before this factor can be saved."
                    elif (scope or 1) == 1 and not gas_type:
                        status, message = "needs_confirmation", "No substance/fuel name found for this row."
                    elif (scope or 1) == 2 and not method:
                        status, message = "needs_confirmation", "No method (location-based/market-based) found for this row."
                    elif (scope or 1) == 3 and not scope3_category:
                        status, message = "needs_confirmation", "No Scope 3 category found for this row."

                    match_name = gas_type or description or scope3_category
                    ipcc_match = _find_ipcc_match(match_name, scope or 1, all_refs)
                    if ipcc_match is not None and value is not None:
                        if normalize(ipcc_match.unit) == normalize(unit or ""):
                            ipcc_match = ipcc_match.model_copy(
                                update={"delta_pct": round((value - ipcc_match.reference_value) / ipcc_match.reference_value * 100, 2)}
                                if ipcc_match.reference_value
                                else {}
                            )

                    factors.append(
                        EFFactorDraft(
                            **common,
                            # True 1-based Excel row number: block_start is
                            # this block's header row (0-based) in the full
                            # combined sheet grid, data starts right after it.
                            row_index=block_start + r + 2,
                            factor_value=value,
                            effective_year=eff_date.year if eff_date else None,
                            version=version_label,
                            included=status not in ("error",),
                            status=status,
                            message=message,
                            raw_cell_text=raw_text,
                            ipcc_match=ipcc_match,
                        )
                    )

            results.append(
                EFSheetDetectionResult(
                    sheet_name=sheet.name,
                    block_index=block_index,
                    scope=scope,
                    scope_score=scope_match.score,
                    scope_rule=scope_match.rule,
                    columns=columns,
                    factors=factors,
                    factor_count=len([f for f in factors if f.status not in ("skip",)]),
                )
            )

    return EFDetectResponse(sheets=results)


def _revalidate(draft: EFFactorDraft) -> tuple[str, str | None]:
    if not draft.included:
        return "skip", None
    if draft.scope not in (1, 2, 3):
        return "error", "Invalid scope."
    if not draft.unit:
        return "error", "Missing unit."
    if draft.factor_value is None:
        return "error", "Missing or non-numeric value."
    if not draft.effective_year:
        return "error", "Missing effective year."
    if not draft.source_reference or not draft.source_reference.strip():
        return "missing_source", "No source reference -- required before this factor can be saved."
    if draft.scope == 1 and not (draft.gas_type or "").strip():
        return "error", "Substance/fuel name is required for a Scope 1 factor."
    if draft.scope == 2 and (draft.method not in ("location-based", "market-based")):
        return "error", "Method must be location-based or market-based for a Scope 2 factor."
    if draft.scope == 3 and not (draft.scope3_category or "").strip():
        return "error", "Scope 3 category is required for a Scope 3 factor."
    return "ready", None


@router.post("/bulk-import", response_model=EFBulkImportResponse)
def bulk_import(
    payload: EFBulkImportRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    """Validates (commit=False) or creates (commit=True) the Admin-reviewed
    factor list from the bulk-upload wizard. Never trusts the client's
    status field -- every row is re-validated against the same rules here,
    including the required source reference. Nothing commits without this
    passing first, and a failed commit row never partially writes."""
    results: list[EFBulkImportResult] = []
    seen: set[tuple] = set()
    ready_count = error_count = created_count = 0

    for draft in payload.factors:
        status, message = _revalidate(draft)

        if status == "ready":
            key = (draft.scope, draft.gas_type, draft.method, draft.scope3_category, draft.unit, draft.effective_year, draft.factor_value)
            if key in seen:
                status, message = "error", "Duplicate row elsewhere in this upload."
            else:
                seen.add(key)

        if status == "skip":
            # Still emit a result, in the same position as the submitted
            # draft -- the wizard correlates results back to rows by index,
            # and one source row can pivot into several drafts sharing the
            # same sheet_name/row_index (e.g. FY25 and FY26 from one row),
            # so silently omitting an entry here would misalign every row
            # after it.
            results.append(EFBulkImportResult(sheet_name=draft.sheet_name, row_index=draft.row_index, status="skip"))
            continue

        if status != "ready":
            error_count += 1
            results.append(EFBulkImportResult(sheet_name=draft.sheet_name, row_index=draft.row_index, status=status, message=message))
            continue

        ready_count += 1
        if not payload.commit:
            results.append(EFBulkImportResult(sheet_name=draft.sheet_name, row_index=draft.row_index, status="ready"))
            continue

        factor = EmissionFactor(
            tenant_id=current.tenant_id,
            scope=draft.scope,
            gas_type=draft.gas_type,
            method=draft.method,
            scope3_category=draft.scope3_category,
            description=draft.description,
            unit=draft.unit,
            factor_value=draft.factor_value,
            effective_date=date(draft.effective_year, 1, 1),
            version=draft.version or f"FY{str(draft.effective_year)[2:]}",
            source=draft.source,
            source_reference=draft.source_reference,
        )
        db.add(factor)
        db.flush()
        created_count += 1
        results.append(EFBulkImportResult(sheet_name=draft.sheet_name, row_index=draft.row_index, status="created", factor_id=factor.id))

    if payload.commit:
        db.commit()

    return EFBulkImportResponse(results=results, ready_count=ready_count, error_count=error_count, created_count=created_count)
