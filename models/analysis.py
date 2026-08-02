"""Analysis plan, deterministic scoring output, recommendation, refusal, and trace."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from models.evidence import EvidencePackage
from models.geography import Geography
from models.metrics import MetricCategory
from models.plan import AnalysisPlanProposal


class LimitationSeverity(StrEnum):
    INFO = "info"
    CAUTION = "caution"
    BLOCKING = "blocking"


class Limitation(BaseModel):
    title: str
    detail: str
    severity: LimitationSeverity = LimitationSeverity.CAUTION


class WeightAdjustment(BaseModel):
    """Disclosure of a renormalization forced by unavailable data."""

    category: MetricCategory
    metric_id: str
    original_weight: float
    reason: str


class TraceAuthority(StrEnum):
    """Who or what is answerable for a trace entry.

    The trace is only an audit log if a reader can tell the difference between something
    the user asked for, something the agent guessed, something a deterministic gate
    decided, and something an API returned. Collapsing those into one undifferentiated
    list of steps is what makes most agent traces unreviewable.
    """

    USER = "user_supplied"
    AGENT = "agent_inference"
    VALIDATION = "deterministic_validation"
    API = "api_evidence"
    HUMAN_APPROVAL = "human_approval"
    CALCULATION = "deterministic_calculation"
    # The narrator falls back to templates with no model configured, so the authority is
    # the explanation layer rather than a model. Which of the two wrote it is in the detail.
    EXPLANATION = "explanation_layer"
    SYSTEM = "system"


AUTHORITY_LABELS: dict[TraceAuthority, str] = {
    TraceAuthority.USER: "User supplied",
    TraceAuthority.AGENT: "Agent inference",
    TraceAuthority.VALIDATION: "Deterministic validation",
    TraceAuthority.API: "API evidence",
    TraceAuthority.HUMAN_APPROVAL: "Human approval",
    TraceAuthority.CALCULATION: "Deterministic calculation",
    TraceAuthority.EXPLANATION: "Explanation layer",
    TraceAuthority.SYSTEM: "System",
}


class TraceEntry(BaseModel):
    """One step in the execution trace shown to the user."""

    step: str
    detail: str
    payload: dict | None = None
    authority: TraceAuthority = TraceAuthority.SYSTEM
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalysisPlan(BaseModel):
    """Structured plan produced by the intent layer.

    The intent layer may only choose from approved geographies and approved metric ids.
    It cannot introduce a datapoint identifier or a value.
    """

    question: str
    geographies: list[Geography]
    metric_ids: list[str]
    category_weights: dict[MetricCategory, float]
    rationale: str
    answerable: bool = True
    interpreted_by: str = "rule_based"


class ScoreBreakdown(BaseModel):
    """Fully exposed intermediate arithmetic for one metric in one region."""

    metric_id: str
    display_name: str
    category: MetricCategory
    evidence_id: str | None
    raw_value: float | None
    normalized_value: float | None
    effective_weight: float
    weighted_contribution: float | None
    included: bool
    exclusion_reason: str | None = None


class CategoryScore(BaseModel):
    category: MetricCategory
    score: float | None
    """0-100, or None when no metric in this category had usable data."""

    category_weight: float
    effective_category_weight: float
    metrics_included: int
    metrics_total: int
    contributions: list[ScoreBreakdown]


class RankedRegion(BaseModel):
    geography: Geography
    rank: int
    overall_score: float | None
    category_scores: list[CategoryScore]
    evidence_completeness: float
    missing_metric_ids: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    leading_region: Geography | None
    ranked_regions: list[RankedRegion]
    narrative: str
    caveats: list[str]
    confidence_label: str
    evidence_completeness: float
    citations: list[str] = Field(default_factory=list)
    generated_by: str = "deterministic_template"


class Refusal(BaseModel):
    """A structured refusal. Emitted instead of, never alongside, a recommendation."""

    question: str
    reason: str
    unsupported_because: list[str]
    required_inputs: list[str]
    offered_alternative: str
    supported_capabilities: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Everything the UI needs. Either ``recommendation`` or ``refusal`` is set, never both."""

    plan: AnalysisPlan | None
    evidence: EvidencePackage | None
    recommendation: Recommendation | None
    refusal: Refusal | None
    limitations: list[Limitation] = Field(default_factory=list)
    weight_adjustments: list[WeightAdjustment] = Field(default_factory=list)
    trace: list[TraceEntry] = Field(default_factory=list)
    reproducibility_hash: str | None = None

    proposal: AnalysisPlanProposal | None = Field(
        default=None,
        description="The approved proposal this run executed, retained for lineage",
    )

    @property
    def refused(self) -> bool:
        return self.refusal is not None

    @property
    def plan_version(self) -> int:
        return self.proposal.version if self.proposal else 1

    def trace_by_authority(self, authority: TraceAuthority) -> list[TraceEntry]:
        return [entry for entry in self.trace if entry.authority == authority]
