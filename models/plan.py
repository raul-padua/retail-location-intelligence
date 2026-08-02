"""The analysis plan as a versioned, auditable contract.

The plan is the mechanism that lets an agent be genuinely useful without being trusted.
Everything the planner produces lands here as a *proposal*: a typed object that states
what would be analysed, what was assumed to get there, what could not be supported, and
what is still unknown. It carries no factual values and no Atlas identifiers, because the
planner is not permitted to emit either.

A proposal is inert. It cannot cause an Atlas call, a score, or a recommendation until it
has passed deterministic validation *and* carries an approval record. The status field is
the gate, and :meth:`AnalysisPlanProposal.can_execute` is the only thing the pipeline
consults.

Revisions do not mutate. An approved plan that the user asks to change produces a child
proposal with ``parent_plan_id`` set and an explicit before/after diff, leaving the
original and its result intact and comparable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from models.geography import Geography
from models.metrics import MetricCategory
from models.strategy import Provenance, RetailStrategyProfile


class PlanStatus(StrEnum):
    DRAFT = "draft"
    """Constructed but not yet checked or shown for review."""

    NEEDS_CLARIFICATION = "needs_clarification"
    """At least one required question is unanswered. Cannot be approved."""

    READY_FOR_REVIEW = "ready_for_review"
    """Passed deterministic validation. Waiting on a human."""

    APPROVED = "approved"
    """A human approved it. This is the only status the pipeline will execute."""

    REJECTED = "rejected"
    EXECUTED = "executed"
    SUPERSEDED = "superseded"
    """Replaced by a later version. Retained so its result stays comparable."""


TERMINAL_STATUSES = {PlanStatus.REJECTED, PlanStatus.SUPERSEDED}


class ClarificationQuestion(BaseModel):
    """A question worth interrupting an executive for, and the reason it qualifies.

    The bar is materiality: the answer must be able to change metric selection, weights,
    geography interpretation, trade-area definition, or whether the analysis is
    supportable at all. Anything that fails that bar is an assumption to disclose, not a
    question to ask.
    """

    model_config = {"frozen": True}

    question_id: str
    question: str
    missing_decision: str = Field(description="The decision that has not been made")
    why_it_matters: str
    affects: list[str] = Field(
        default_factory=list,
        description="Parts of the analysis the answer could change",
    )
    required: bool = False
    """Required questions block execution. Optional ones proceed on a disclosed default."""

    safe_default: str | None = Field(
        default=None,
        description="What the planner will assume if this is left unanswered",
    )
    answer: str | None = None

    @property
    def answered(self) -> bool:
        return bool(self.answer and self.answer.strip())

    @property
    def blocks_execution(self) -> bool:
        return self.required and not self.answered


class Assumption(BaseModel):
    """Something the planner filled in, recorded so the user can overrule it."""

    model_config = {"frozen": True}

    subject: str
    assumption: str
    basis: str = Field(description="Why the planner concluded this")
    provenance: Provenance = Provenance.PLANNER_INFERRED
    reversible_by: str | None = Field(
        default=None, description="What the user can change to overrule it"
    )


class UnsupportedRequirement(BaseModel):
    """A dimension the user asked for that no available data can express."""

    model_config = {"frozen": True}

    requirement: str
    why_unavailable: str
    would_require: str = Field(description="The data source that would supply it")
    capability_id: str | None = Field(
        default=None, description="Capability registry entry describing the future path"
    )


class RejectedField(BaseModel):
    """A planner output that failed revalidation, kept so the trace can show it."""

    model_config = {"frozen": True}

    field: str
    offending_value: str
    reason: str


class PlannerProvenance(BaseModel):
    """Who built this plan and what of theirs was thrown away."""

    model_config = {"frozen": True}

    planner: str = Field(description="'deterministic' or 'llm'")
    model: str | None = None
    fell_back: bool = False
    fallback_reason: str | None = None
    rejected_fields: list[RejectedField] = Field(default_factory=list)

    @property
    def is_deterministic(self) -> bool:
        return self.planner == "deterministic"

    def describe(self) -> str:
        if self.is_deterministic:
            return "Deterministic planner (no language model involved)"
        base = f"Language model planner ({self.model})"
        if self.rejected_fields:
            base += f", with {len(self.rejected_fields)} field(s) rejected by validation"
        if self.fell_back:
            base += "; fell back to the deterministic plan"
        return base


class PlanEdit(BaseModel):
    """A change a human made to the proposal before approving it."""

    model_config = {"frozen": True}

    field: str
    before: Any = None
    after: Any = None
    edited_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApprovalRecord(BaseModel):
    """Evidence that a human authorized this analysis."""

    model_config = {"frozen": True}

    approved: bool = False
    approved_at: datetime | None = None
    approved_by: str = "user"
    edits: list[PlanEdit] = Field(default_factory=list)
    note: str | None = None

    @classmethod
    def approve(cls, edits: list[PlanEdit] | None = None, note: str | None = None):
        return cls(
            approved=True,
            approved_at=datetime.now(UTC),
            edits=edits or [],
            note=note,
        )


class PlanValidationStatus(StrEnum):
    NOT_VALIDATED = "not_validated"
    PASSED = "passed"
    FAILED = "failed"


class PlanCheck(BaseModel):
    """One deterministic gate applied to the proposal."""

    model_config = {"frozen": True}

    name: str
    passed: bool
    detail: str
    blocking: bool = True


class PlanValidationReport(BaseModel):
    model_config = {"frozen": True}

    status: PlanValidationStatus = PlanValidationStatus.NOT_VALIDATED
    checks: list[PlanCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclosures: list[str] = Field(
        default_factory=list,
        description="Adjustments the validator made, which must be shown, never silent",
    )

    @property
    def passed(self) -> bool:
        return self.status == PlanValidationStatus.PASSED

    @property
    def failures(self) -> list[PlanCheck]:
        return [check for check in self.checks if not check.passed and check.blocking]


def new_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:12]}"


class AnalysisPlanProposal(BaseModel):
    """What the agent proposes to analyse. Never what it concluded.

    Contains no factual value, no Atlas datapoint identifier, and no score. The planner
    works in metric ids and geography slugs drawn from allowlists; the registry is the
    only thing that maps a metric id to an Atlas identifier, and it does so at execution
    time, well after this object has been approved.
    """

    model_config = {"frozen": True}

    plan_id: str = Field(default_factory=new_plan_id)
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: PlanStatus = PlanStatus.DRAFT

    original_request: str = ""
    sanitized_request: str = ""

    retail_strategy_profile: RetailStrategyProfile = Field(
        default_factory=RetailStrategyProfile
    )
    candidate_geographies: list[Geography] = Field(default_factory=list)
    selected_metric_ids: list[str] = Field(default_factory=list)
    category_weights: dict[MetricCategory, float] = Field(default_factory=dict)
    metric_weight_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Optional per-metric weight, replacing the registry default",
    )

    assumptions: list[Assumption] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    unsupported_requirements: list[UnsupportedRequirement] = Field(default_factory=list)
    excluded_requirements: list[str] = Field(
        default_factory=list,
        description="Things the user asked for that were dropped, with the reason",
    )

    planner_rationale: str = ""
    expected_outputs: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)

    approval_record: ApprovalRecord = Field(default_factory=ApprovalRecord)
    parent_plan_id: str | None = None
    revision_summary: str | None = None
    planner_provenance: PlannerProvenance = Field(
        default_factory=lambda: PlannerProvenance(planner="deterministic")
    )
    validation: PlanValidationReport = Field(default_factory=PlanValidationReport)

    # ------------------------------------------------------------------ gates

    @property
    def unanswered_required_questions(self) -> list[ClarificationQuestion]:
        return [q for q in self.clarification_questions if q.blocks_execution]

    @property
    def can_approve(self) -> bool:
        """Whether a human is even allowed to approve this.

        Deliberately does not consider whether they *have* approved it: that is
        :attr:`can_execute`. Approval is only offered once the deterministic gates pass.
        """
        return (
            self.validation.passed
            and not self.unanswered_required_questions
            and self.status
            in {PlanStatus.DRAFT, PlanStatus.READY_FOR_REVIEW, PlanStatus.NEEDS_CLARIFICATION}
        )

    @property
    def can_execute(self) -> bool:
        """The single condition the pipeline consults before touching Atlas."""
        return (
            self.status == PlanStatus.APPROVED
            and self.approval_record.approved
            and self.validation.passed
            and not self.unanswered_required_questions
        )

    # ------------------------------------------------------------- transitions

    def approved(self, edits: list[PlanEdit] | None = None, note: str | None = None):
        if not self.can_approve:
            raise PlanNotApprovableError(self)
        return self.model_copy(
            update={
                "status": PlanStatus.APPROVED,
                "approval_record": ApprovalRecord.approve(edits=edits, note=note),
            }
        )

    def rejected(self, note: str | None = None):
        return self.model_copy(
            update={
                "status": PlanStatus.REJECTED,
                "approval_record": ApprovalRecord(approved=False, note=note),
            }
        )

    def executed(self):
        return self.model_copy(update={"status": PlanStatus.EXECUTED})

    def superseded(self):
        return self.model_copy(update={"status": PlanStatus.SUPERSEDED})

    def answered(self, answers: dict[str, str]):
        """Attach clarification answers, marking them as user-supplied."""
        updated = [
            question.model_copy(update={"answer": answers[question.question_id]})
            if question.question_id in answers and answers[question.question_id].strip()
            else question
            for question in self.clarification_questions
        ]
        return self.model_copy(update={"clarification_questions": updated})


class PlanNotApprovableError(RuntimeError):
    """Raised when approval is attempted on a plan that has not passed its gates."""

    def __init__(self, plan: AnalysisPlanProposal) -> None:
        self.plan = plan
        blocking = [check.name for check in plan.validation.failures]
        unanswered = [q.question_id for q in plan.unanswered_required_questions]
        super().__init__(
            f"Plan {plan.plan_id} v{plan.version} cannot be approved. "
            f"Failed checks: {blocking or 'none'}. "
            f"Unanswered required questions: {unanswered or 'none'}."
        )


class PlanNotApprovedError(RuntimeError):
    """Raised when execution is attempted on a plan that carries no approval."""

    def __init__(self, plan: AnalysisPlanProposal) -> None:
        self.plan = plan
        super().__init__(
            f"Plan {plan.plan_id} v{plan.version} has status {plan.status} and cannot be "
            "executed. A plan must pass deterministic validation and carry a human "
            "approval record before any Atlas call is made."
        )


class PlanRevisionProposal(BaseModel):
    """A proposed change to an approved plan. Inert until confirmed.

    The assistant produces these instead of acting. Showing the exact before and after,
    and requiring a confirmation, is what keeps a conversational surface from quietly
    becoming a control surface.
    """

    model_config = {"frozen": True}

    revision_id: str = Field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:10]}")
    parent_plan_id: str
    parent_version: int = 1
    requested_change: str = Field(description="The user's request, sanitized")
    changed_fields: list[str] = Field(default_factory=list)
    before_values: dict[str, Any] = Field(default_factory=dict)
    proposed_values: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    expected_effect: str = Field(
        default="",
        description="Directional and hedged. Never a claimed result.",
    )
    validation: PlanValidationReport = Field(default_factory=PlanValidationReport)
    requires_confirmation: bool = True
    unsupported_parts: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_actionable(self) -> bool:
        return bool(self.changed_fields) and self.validation.passed
