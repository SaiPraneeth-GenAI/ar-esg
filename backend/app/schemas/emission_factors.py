import uuid
from datetime import date

from pydantic import BaseModel, model_validator

VALID_METHODS = {"location-based", "market-based"}


class EmissionFactorOut(BaseModel):
    id: uuid.UUID
    scope: int
    gas_type: str | None
    method: str | None
    scope3_category: str | None
    description: str | None
    unit: str
    factor_value: float
    effective_year: int
    version: str
    source: str | None
    source_reference: str | None
    ipcc_reference_key: uuid.UUID | None = None


class EmissionFactorCreate(BaseModel):
    scope: int
    gas_type: str | None = None
    method: str | None = None
    scope3_category: str | None = None
    description: str | None = None
    unit: str
    factor_value: float
    effective_year: int
    source: str | None = None
    source_reference: str
    # Set when this factor was created via the IPCC-assisted panel -- links
    # back to the seeded reference row it came from, even if the user
    # edited the value before saving.
    ipcc_reference_key: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_scope_shape(self) -> "EmissionFactorCreate":
        if self.scope not in (1, 2, 3):
            raise ValueError("scope must be 1, 2, or 3")
        if not self.source_reference or not self.source_reference.strip():
            raise ValueError("source_reference is required -- a factor with no traceable citation cannot be saved")
        if self.scope == 1 and not (self.gas_type or "").strip():
            raise ValueError("gas_type (substance/fuel name) is required for a Scope 1 factor")
        if self.scope == 2:
            if not (self.method or "").strip():
                raise ValueError("method is required for a Scope 2 factor")
            if self.method not in VALID_METHODS:
                raise ValueError(f"method must be one of {sorted(VALID_METHODS)}")
        if self.scope == 3 and not (self.scope3_category or "").strip():
            raise ValueError("scope3_category is required for a Scope 3 factor")
        return self


# ---- IPCC reference (seeded, read-only) -----------------------------------


class IpccSearchResult(BaseModel):
    substance_name: str
    scope: int
    factor_type: str
    latest_effective_year: int
    latest_publication: str


class IpccVersionOut(BaseModel):
    id: uuid.UUID
    substance_name: str
    scope: int
    factor_type: str
    publication: str
    effective_year: int
    ncv_mj_per_unit: float | None
    density_kg_per_unit: float | None
    co2_ef_per_tj: float | None
    oxidation_factor: float | None
    derived_factor_value: float
    unit: str
    source_reference: str


class IpccMatch(BaseModel):
    substance_name: str
    publication: str
    effective_year: int
    reference_value: float
    unit: str
    delta_pct: float | None  # null if units differ and a % comparison isn't meaningful


# ---- Bulk upload ----------------------------------------------------------


class EFSheetInput(BaseModel):
    name: str
    filename: str
    headers: list[str]
    rows: list[list[str]]
    # Admin-confirmed column roles from the mapping step, keyed by
    # "{block_index}:{column_index}" -- a sheet can hold more than one
    # table (see split_into_blocks), and the same column position means
    # something different in each one, so the block has to be part of the
    # key. Overrides whatever classify_columns() would have guessed for
    # that column -- this is how "mark this column skip -- not a factor"
    # actually takes effect, and how a re-detect after the mapping step is
    # re-triggered.
    column_overrides: dict[str, str] | None = None


class EFDetectRequest(BaseModel):
    sheets: list[EFSheetInput]
    # Fallback effective year for any pivoted row that has no year/version
    # token of its own (e.g. a Scope 3 sheet's plain, non-year "Emission
    # Factor" column) -- same "selected value at the top of the screen"
    # fallback pattern used by entries bulk-upload.
    default_effective_year: int | None = None
    # Fallback Scope 2 method -- the real Grid Energy table has no
    # per-row location-based/market-based column at all, so without this
    # every single Scope 2 row would need manual confirmation.
    default_method: str | None = None


class EFColumnSuggestion(BaseModel):
    header: str
    index: int
    role: str  # name | method | scope3_category | description | unit | source | source_reference | value | year_value | skip
    year_label: str | None = None
    score: float
    rule: str


class EFFactorDraft(BaseModel):
    sheet_name: str
    block_index: int
    row_index: int  # 1-based row within the sheet, for the customer to trace back
    scope: int
    gas_type: str | None = None
    method: str | None = None
    scope3_category: str | None = None
    description: str | None = None
    unit: str | None = None
    factor_value: float | None = None
    effective_year: int | None = None
    version: str | None = None
    source: str | None = None
    source_reference: str | None = None
    included: bool = True
    status: str = "unchecked"  # ready | needs_confirmation | missing_source | error | skip | unchecked | created
    message: str | None = None
    raw_cell_text: str | None = None
    # Read-only, informational -- never overwrites the uploaded value.
    ipcc_match: IpccMatch | None = None


class EFSheetDetectionResult(BaseModel):
    sheet_name: str
    block_index: int
    scope: int | None
    scope_score: float
    scope_rule: str
    columns: list[EFColumnSuggestion]
    factors: list[EFFactorDraft]
    factor_count: int


class EFDetectResponse(BaseModel):
    sheets: list[EFSheetDetectionResult]


class EFBulkImportRequest(BaseModel):
    commit: bool = False
    factors: list[EFFactorDraft]


class EFBulkImportResult(BaseModel):
    sheet_name: str
    row_index: int
    status: str
    message: str | None = None
    factor_id: uuid.UUID | None = None


class EFBulkImportResponse(BaseModel):
    results: list[EFBulkImportResult]
    ready_count: int
    error_count: int
    created_count: int
