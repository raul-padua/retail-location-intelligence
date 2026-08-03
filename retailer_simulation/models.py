"""Typed models for the NorthStar Apparel fictional retailer simulator."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from models.provenance import DataClass

SIMULATOR_VERSION = "northstar_v1"
BRAND_NAME = "NorthStar Apparel"

DEFAULT_FORMAT_MIX: dict[str, float] = {
    "mall": 0.35,
    "strip": 0.40,
    "outlet": 0.25,
}

FORMAT_SALES_MULTIPLIERS: dict[str, float] = {
    "mall": 1.12,
    "strip": 1.0,
    "outlet": 0.78,
}

FORMAT_SQFT_MULTIPLIERS: dict[str, float] = {
    "mall": 1.05,
    "strip": 1.0,
    "outlet": 0.85,
}


class VerificationState(StrEnum):
    VERIFIED = "VERIFIED"
    DEMO_DEFAULT = "DEMO_DEFAULT"
    UNVERIFIED_DISABLED = "UNVERIFIED_DISABLED"


class Benchmark(BaseModel):
    model_config = {"frozen": True}

    metric: str
    value: float
    unit: str
    source_name: str
    source_url: str | None = None
    source_period: str | None = None
    verification_state: VerificationState
    usage: str
    data_class: DataClass = DataClass.PUBLIC_COMPANY_BENCHMARK


class BenchmarkCatalog(BaseModel):
    model_config = {"frozen": True}

    version: str
    brand: str
    provenance_notes: list[str] = Field(default_factory=list)
    benchmarks: list[Benchmark] = Field(default_factory=list)


class RetailerScenario(BaseModel):
    """Explicit scenario inputs — treated as user assumptions, not measured data."""

    model_config = {"frozen": True}

    store_count: int = Field(default=48, ge=1, le=500)
    format_mix: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_FORMAT_MIX))
    seed: int = Field(default=42)
    sales_target_usd: float = Field(default=200_000_000.0, gt=0)
    margin_min_pct: float = Field(default=34.0, ge=0.0, le=100.0)
    margin_max_pct: float = Field(default=42.0, ge=0.0, le=100.0)
    data_class: DataClass = DataClass.USER_ASSUMPTION

    @field_validator("format_mix")
    @classmethod
    def _normalize_format_mix(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("format_mix must include at least one format")
        total = sum(value.values())
        if total <= 0:
            raise ValueError("format_mix weights must sum to a positive value")
        return {key: weight / total for key, weight in value.items()}

    @field_validator("margin_max_pct")
    @classmethod
    def _margin_range(cls, value: float, info) -> float:
        minimum = info.data.get("margin_min_pct")
        if minimum is not None and value < minimum:
            raise ValueError("margin_max_pct must be >= margin_min_pct")
        return value


class SimulatedStore(BaseModel):
    model_config = {"frozen": True}

    store_id: str
    name: str
    format: str
    city: str
    state: str
    lat: float
    lon: float
    sq_ft: float
    annual_sales_usd: float
    gross_margin_pct: float
    host_geoid: str | None = None
    host_name: str | None = None
    host_cluster_id: str | None = None
    data_class: DataClass = DataClass.SIMULATED_RETAILER_DATA


class MonthlyPerformance(BaseModel):
    model_config = {"frozen": True}

    month: int
    label: str
    total_sales_usd: float
    store_count: int
    data_class: DataClass = DataClass.SIMULATED_RETAILER_DATA


class SegmentShare(BaseModel):
    model_config = {"frozen": True}

    segment_id: str
    label: str
    share_pct: float
    data_class: DataClass = DataClass.SIMULATED_RETAILER_DATA


class ReconciliationLine(BaseModel):
    model_config = {"frozen": True}

    metric: str
    target: float
    generated: float
    tolerance_pct: float
    passed: bool
    note: str
    data_class: DataClass = DataClass.SIMULATED_RETAILER_DATA


class SimulationArtifact(BaseModel):
    model_config = {"frozen": True}

    brand: str = BRAND_NAME
    simulator_version: str = SIMULATOR_VERSION
    seed: int
    scenario: RetailerScenario
    stores: list[SimulatedStore]
    monthly: list[MonthlyPerformance]
    segments: list[SegmentShare]
    reconciliation: list[ReconciliationLine]
    assumptions: list[str] = Field(default_factory=list)
    provenance_notes: list[str] = Field(default_factory=list)
    data_class: DataClass = DataClass.SIMULATED_RETAILER_DATA
    reconciliation_passed: bool = False
