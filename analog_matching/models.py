"""Typed models for analog-store matching."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from models.provenance import DataClass


class AnalogyStrength(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class FeatureContribution(BaseModel):
    model_config = {"frozen": True}

    feature_id: str
    display_name: str
    candidate_value: float | None
    store_value: float | None
    weight: float
    signed_contribution: float


class PerformanceSummary(BaseModel):
    """Attached only after ranking for display — never used in distance."""

    model_config = {"frozen": True}

    median_annual_sales_usd: float
    iqr_annual_sales_usd: tuple[float, float]
    median_gross_margin_pct: float
    iqr_gross_margin_pct: tuple[float, float]
    data_class: DataClass = DataClass.SIMULATED_RETAILER_DATA


class AnalogMatch(BaseModel):
    model_config = {"frozen": True}

    store_id: str
    store_name: str
    format: str
    host_geoid: str
    host_name: str
    similarity: float
    distance: float
    contributions: list[FeatureContribution]
    mismatches: list[str] = Field(default_factory=list)
    performance_summary: PerformanceSummary | None = None
    data_class: DataClass = DataClass.PUBLIC_MARKET_DATA


class AggregateRange(BaseModel):
    model_config = {"frozen": True}

    min_similarity: float
    max_similarity: float
    median_similarity: float
    data_class: DataClass = DataClass.PUBLIC_MARKET_DATA


class AnalogSearchResult(BaseModel):
    model_config = {"frozen": True}

    candidate_market_id: str
    candidate_geoid: str
    candidate_name: str
    candidate_cluster_id: str
    matches: list[AnalogMatch]
    aggregate_range: AggregateRange | None = None
    analogy_strength: AnalogyStrength
    warnings: list[str] = Field(default_factory=list)
    feature_ids: tuple[str, ...]
    matcher_version: str
    feature_set_version: str
    context_pack: list[str] = Field(default_factory=list)
    data_class: DataClass = DataClass.PUBLIC_MARKET_DATA
