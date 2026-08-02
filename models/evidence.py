"""Evidence objects: the only factual currency the explanation layer is allowed to spend."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from models.geography import Geography
from models.metrics import MetricDefinition


class ValidationStatus(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    """Atlas returned no value for this geography/datapoint pair."""

    SCHEMA_INVALID = "schema_invalid"
    """The response did not match the documented Atlas response shape."""

    INCOMPARABLE_PERIOD = "incomparable_period"
    INCOMPARABLE_GEOGRAPHY = "incomparable_geography"
    INCOMPARABLE_UNIT = "incomparable_unit"
    INCOMPARABLE_SOURCE = "incomparable_source"


class RawCall(BaseModel):
    """A recorded Atlas request/response pair, credential-redacted, for traceability."""

    call_id: str
    method: str
    url: str
    request_body: dict | None = None
    response_body: dict | None = None
    status_code: int | None = None
    elapsed_seconds: float | None = None
    attempts: int = 1
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.status_code is not None and 200 <= self.status_code < 300


class EvidenceItem(BaseModel):
    """One observed value, fully attributed.

    Nothing downstream may state a number that is not present on one of these objects.
    ``normalized_value`` and ``weighted_contribution`` are filled in by the scoring service.
    """

    evidence_id: str
    metric: MetricDefinition
    geography: Geography
    atlas_datapoint: str
    raw_value: float | None
    period: str | None
    source: str | None
    reported_geography: str | None = Field(
        default=None,
        description="Geography Atlas actually answered with; differs when context shifts",
    )
    margin_of_error: float | None = None
    validation_status: ValidationStatus = ValidationStatus.VALID
    validation_notes: list[str] = Field(default_factory=list)
    call_id: str | None = None
    normalized_value: float | None = None
    weighted_contribution: float | None = None

    @property
    def is_usable(self) -> bool:
        return self.validation_status == ValidationStatus.VALID and self.raw_value is not None

    @property
    def geography_context_shifted(self) -> bool:
        return bool(self.reported_geography) and self.reported_geography != self.geography.slug

    def citation(self) -> str:
        """Compact inline citation the explanation layer must attach to every claim."""
        return (
            f"[{self.atlas_datapoint} | {self.geography.slug} | "
            f"{self.period or 'period n/a'} | {self.source or 'source n/a'}]"
        )


class ExcludedMetric(BaseModel):
    """A metric that was requested but did not survive validation, with the reason."""

    metric_id: str
    display_name: str
    atlas_datapoint: str
    reason: str
    status: ValidationStatus
    affected_geographies: list[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    """The validated, immutable bundle handed to scoring and then to explanation."""

    package_id: str
    geographies: list[Geography]
    items: list[EvidenceItem]
    excluded_metrics: list[ExcludedMetric] = Field(default_factory=list)
    raw_calls: list[RawCall] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def usable_items(self) -> list[EvidenceItem]:
        return [item for item in self.items if item.is_usable]

    def for_metric(self, metric_id: str) -> list[EvidenceItem]:
        return [item for item in self.items if item.metric.metric_id == metric_id]

    def for_geography(self, slug: str) -> list[EvidenceItem]:
        return [item for item in self.items if item.geography.slug == slug]

    def by_id(self, evidence_id: str) -> EvidenceItem | None:
        return next((item for item in self.items if item.evidence_id == evidence_id), None)

    @property
    def completeness(self) -> float:
        """Share of attempted geography/metric cells that produced a usable value."""
        if not self.items:
            return 0.0
        return len(self.usable_items()) / len(self.items)
