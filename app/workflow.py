"""The plan lifecycle as an explicit state machine.

This is the part of the system that most wanted to be an autonomous loop, and most needed
not to be. The interesting property of a governed agent is not that it can decide what to
do next - it is that a reader can point at any state it reached and say how it got there
and who authorized the move. A loop makes that a matter of reading logs; a state machine
makes it a matter of reading the transition table.

So: five stages, a fixed set of transitions between them, and an exception for anything
else. ``execute`` cannot be reached from ``CLARIFY``. ``approve`` cannot be called on a
plan that failed validation. A revision cannot run without passing back through approval.
These are enforced here rather than in the UI, which is why the UI is not the thing under
test.

The module holds no Streamlit import on purpose. Streamlit owns the widgets and the
session dictionary; this owns the rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from core.config import Settings, get_settings
from metrics.registry import MetricRegistry, get_registry
from models.analysis import AnalysisResult, Refusal, TraceAuthority, TraceEntry
from models.metrics import MetricCategory
from models.plan import (
    AnalysisPlanProposal,
    PlanEdit,
    PlanRevisionProposal,
    PlanStatus,
)
from orchestration.comparison import PlanDiff, ResultDiff, diff_plans, diff_results
from orchestration.pipeline import AnalysisPipeline
from planning.deterministic import PlanningRequest
from planning.planner import PlanningOutcome, propose_plan
from planning.revision import apply_revision, propose_revision
from planning.validation import validate_plan


class Stage(StrEnum):
    DESCRIBE = "describe"
    """Waiting for a business objective and candidate regions."""

    CLARIFY = "clarify"
    """The planner asked material questions. Execution is unreachable from here."""

    REVIEW = "review"
    """A validated proposal is on the table, waiting on a human."""

    EXECUTED = "executed"
    """The approved plan ran. Results and prior versions are retained."""

    REFUSED = "refused"
    """The objective was refused before a planner ran. Terminal until reset."""


class WorkflowError(RuntimeError):
    """An illegal transition. Raised rather than silently corrected."""


@dataclass(frozen=True)
class ExecutedVersion:
    """One executed plan version and the result it produced, kept for comparison."""

    plan: AnalysisPlanProposal
    result: AnalysisResult

    @property
    def label(self) -> str:
        return f"v{self.plan.version}"


@dataclass
class WorkflowState:
    """Everything the UI renders, and nothing it computes."""

    stage: Stage = Stage.DESCRIBE

    objective: str = ""
    geographies: list[str] = field(default_factory=list)
    store_format: str | None = None
    target_segments: str | None = None
    retailer_type: str | None = None

    plan: AnalysisPlanProposal | None = None
    planning_trace: list[TraceEntry] = field(default_factory=list)
    refusal: Refusal | None = None

    history: list[ExecutedVersion] = field(default_factory=list)
    pending_revision: PlanRevisionProposal | None = None
    notice: str | None = None

    # ----------------------------------------------------------------- queries

    @property
    def current(self) -> ExecutedVersion | None:
        return self.history[-1] if self.history else None

    @property
    def result(self) -> AnalysisResult | None:
        return self.current.result if self.current else None

    @property
    def previous(self) -> ExecutedVersion | None:
        return self.history[-2] if len(self.history) > 1 else None

    @property
    def can_approve(self) -> bool:
        return self.stage == Stage.REVIEW and self.plan is not None and self.plan.can_approve

    @property
    def open_questions(self) -> list:
        return self.plan.clarification_questions if self.plan else []

    def plan_diff(self) -> PlanDiff | None:
        if self.previous is None or self.current is None:
            return None
        return diff_plans(self.previous.plan, self.current.plan)

    def result_diff(self) -> ResultDiff | None:
        if self.previous is None or self.current is None:
            return None
        return diff_results(self.previous.result, self.current.result)


# --------------------------------------------------------------------- transitions


def _stage_for(plan: AnalysisPlanProposal) -> Stage:
    return (
        Stage.CLARIFY
        if plan.status == PlanStatus.NEEDS_CLARIFICATION or plan.unanswered_required_questions
        else Stage.REVIEW
    )


def describe(
    state: WorkflowState,
    objective: str,
    geographies: list[str],
    *,
    retailer_type: str | None = None,
    store_format: str | None = None,
    target_segments: str | None = None,
    settings: Settings | None = None,
    registry: MetricRegistry | None = None,
    use_llm: bool = True,
) -> WorkflowState:
    """Step 1. Interpret the objective into a proposal, or refuse it."""
    settings = settings or get_settings()

    request = PlanningRequest(
        objective=objective,
        geographies=list(geographies),
        retailer_type=retailer_type,
        store_format=store_format,
        target_segments=target_segments,
    )
    outcome = propose_plan(request, settings=settings, registry=registry, use_llm=use_llm)

    base = replace(
        state,
        objective=objective,
        geographies=list(geographies),
        retailer_type=retailer_type,
        store_format=store_format,
        target_segments=target_segments,
        planning_trace=list(outcome.trace),
        pending_revision=None,
        notice=None,
    )

    if outcome.refused:
        return replace(base, stage=Stage.REFUSED, plan=None, refusal=outcome.refusal)

    plan = outcome.plan
    assert plan is not None
    return replace(base, stage=_stage_for(plan), plan=plan, refusal=None)


def answer(
    state: WorkflowState,
    answers: dict[str, str],
    *,
    settings: Settings | None = None,
    registry: MetricRegistry | None = None,
    use_llm: bool = True,
) -> WorkflowState:
    """Step 2. Feed clarification answers back through the planner.

    Answers re-plan rather than patch. An answer about store format can change which
    metrics belong in the plan, so applying it as a field edit would leave the rest of the
    proposal reflecting an assumption the user just overruled.
    """
    if state.stage not in {Stage.CLARIFY, Stage.REVIEW}:
        raise WorkflowError(f"Cannot answer clarifications from stage {state.stage}.")
    if state.plan is None:
        raise WorkflowError("There is no plan to answer questions about.")

    supplied = {key: value for key, value in answers.items() if value and value.strip()}

    request = PlanningRequest(
        objective=state.objective,
        geographies=list(state.geographies),
        retailer_type=state.retailer_type,
        store_format=state.store_format,
        target_segments=state.target_segments,
        answers=supplied,
    )
    outcome = propose_plan(
        request, settings=settings or get_settings(), registry=registry, use_llm=use_llm
    )

    if outcome.refused:
        return replace(
            state,
            stage=Stage.REFUSED,
            plan=None,
            refusal=outcome.refusal,
            planning_trace=[*state.planning_trace, *outcome.trace],
        )

    plan = outcome.plan
    assert plan is not None
    trace = [
        *state.planning_trace,
        TraceEntry(
            step="clarifications_answered",
            detail=f"{len(supplied)} clarification answer(s) supplied by the user.",
            authority=TraceAuthority.USER,
            payload={"answers": supplied},
        ),
        *outcome.trace,
    ]
    return replace(state, stage=_stage_for(plan), plan=plan, planning_trace=trace)


def edit(
    state: WorkflowState,
    *,
    category_weights: dict[MetricCategory, float] | None = None,
    selected_metric_ids: list[str] | None = None,
    geographies: list[str] | None = None,
    registry: MetricRegistry | None = None,
) -> WorkflowState:
    """Step 4a. Apply human edits, record them, and revalidate.

    A human edit is not exempt from validation. It is recorded as a ``PlanEdit`` so the
    trace can distinguish what the planner proposed from what the user overrode, and the
    edited plan goes back through the same gate.
    """
    if state.stage not in {Stage.REVIEW, Stage.CLARIFY}:
        raise WorkflowError(f"Cannot edit a plan from stage {state.stage}.")
    if state.plan is None:
        raise WorkflowError("There is no plan to edit.")

    plan = state.plan
    edits: list[PlanEdit] = list(plan.approval_record.edits)
    update: dict = {}

    if category_weights is not None:
        total = sum(category_weights.values())
        if total <= 0:
            raise WorkflowError("At least one category weight must be greater than zero.")
        normalized = {category: weight / total for category, weight in category_weights.items()}
        if normalized != plan.category_weights:
            edits.append(
                PlanEdit(
                    field="category_weights",
                    before={str(k): round(v, 4) for k, v in plan.category_weights.items()},
                    after={str(k): round(v, 4) for k, v in normalized.items()},
                )
            )
            update["category_weights"] = normalized

    if selected_metric_ids is not None:
        chosen = list(dict.fromkeys(selected_metric_ids))
        if chosen != plan.selected_metric_ids:
            edits.append(
                PlanEdit(
                    field="selected_metric_ids",
                    before=list(plan.selected_metric_ids),
                    after=chosen,
                )
            )
            update["selected_metric_ids"] = chosen

    if geographies is not None:
        from orchestration.intent import resolve_candidate_geographies

        resolved, unresolved = resolve_candidate_geographies(geographies)
        if unresolved:
            raise WorkflowError(
                "These regions are not licensed by the active token: "
                + ", ".join(unresolved)
            )
        current = [geography.slug for geography in plan.candidate_geographies]
        if [geography.slug for geography in resolved] != current:
            edits.append(
                PlanEdit(
                    field="candidate_geographies",
                    before=current,
                    after=[geography.slug for geography in resolved],
                )
            )
            update["candidate_geographies"] = resolved

    if not update:
        return state

    update["approval_record"] = plan.approval_record.model_copy(update={"edits": edits})
    edited = validate_plan(plan.model_copy(update=update), registry)

    trace = [
        *state.planning_trace,
        TraceEntry(
            step="human_plan_edit",
            detail=f"The user edited {len(update) - 1} field(s) of the proposal.",
            authority=TraceAuthority.HUMAN_APPROVAL,
            payload={
                "edits": [
                    {"field": entry.field, "before": entry.before, "after": entry.after}
                    for entry in edits
                ],
                "revalidated_status": str(edited.validation.status),
            },
        ),
    ]
    return replace(state, plan=edited, stage=_stage_for(edited), planning_trace=trace)


def reject(state: WorkflowState, note: str | None = None) -> WorkflowState:
    """Step 4b. Throw the proposal away and go back to the objective."""
    if state.plan is None:
        raise WorkflowError("There is no plan to reject.")

    trace = [
        *state.planning_trace,
        TraceEntry(
            step="plan_rejected",
            detail="The user rejected the proposed plan.",
            authority=TraceAuthority.HUMAN_APPROVAL,
            payload={"plan_id": state.plan.plan_id, "note": note},
        ),
    ]
    return replace(
        state,
        stage=Stage.DESCRIBE,
        plan=state.plan.rejected(note=note),
        planning_trace=trace,
        notice="Plan rejected. Adjust the objective and propose a new one.",
    )


def approve_and_run(
    state: WorkflowState,
    pipeline: AnalysisPipeline,
    *,
    note: str | None = None,
    use_llm_narrative: bool = True,
) -> WorkflowState:
    """Steps 4c and 5. The only path from a proposal to an Atlas call."""
    if state.stage != Stage.REVIEW:
        raise WorkflowError(
            f"A plan can only be approved from the review stage, not {state.stage}."
        )
    if state.plan is None:
        raise WorkflowError("There is no plan to approve.")
    if not state.plan.can_approve:
        raise WorkflowError(
            "This plan has not passed deterministic validation and cannot be approved."
        )

    approved = state.plan.approved(note=note)
    result = pipeline.run_approved(
        approved,
        use_llm_narrative=use_llm_narrative,
        planning_trace=state.planning_trace,
    )
    executed = result.proposal or approved.executed()

    return replace(
        state,
        stage=Stage.EXECUTED,
        plan=executed,
        history=[*state.history, ExecutedVersion(plan=executed, result=result)],
        pending_revision=None,
        notice=None,
    )


# ------------------------------------------------------------------------ revisions


def propose(state: WorkflowState, message: str) -> WorkflowState:
    """Park a proposed revision. Nothing runs; the UI renders it for confirmation."""
    if state.stage != Stage.EXECUTED or state.plan is None:
        raise WorkflowError("A revision can only be proposed against an executed plan.")

    revision = propose_revision(message, state.plan)
    if revision is None:
        return replace(
            state, notice="I could not read that as a change to the analysis."
        )
    return replace(state, pending_revision=revision, notice=None)


def discard_revision(state: WorkflowState) -> WorkflowState:
    return replace(state, pending_revision=None, notice="Revision discarded.")


def confirm_revision(
    state: WorkflowState,
    pipeline: AnalysisPipeline,
    *,
    registry: MetricRegistry | None = None,
    use_llm_narrative: bool = True,
) -> WorkflowState:
    """Confirm a parked revision: new version, fresh approval, fresh run.

    The previous version is marked superseded rather than discarded, and its result stays
    in ``history`` so the two can be compared.
    """
    if state.pending_revision is None:
        raise WorkflowError("There is no revision awaiting confirmation.")
    if state.plan is None or state.stage != Stage.EXECUTED:
        raise WorkflowError("A revision can only be confirmed against an executed plan.")

    revision = state.pending_revision
    revised = apply_revision(state.plan, revision, registry)

    if not revised.can_approve:
        return replace(
            state,
            plan=revised,
            stage=_stage_for(revised),
            pending_revision=None,
            notice=(
                "The revised plan did not pass validation, so it was not run. "
                "Review it before approving."
            ),
        )

    confirmation = TraceEntry(
        step="revision_confirmed",
        detail=f"The user confirmed revision {revision.revision_id}.",
        authority=TraceAuthority.HUMAN_APPROVAL,
        payload={
            "revision_id": revision.revision_id,
            "requested_change": revision.requested_change,
            "changed_fields": revision.changed_fields,
            "before": revision.before_values,
            "after": revision.proposed_values,
            "parent_plan_id": revision.parent_plan_id,
            "parent_version": revision.parent_version,
            "new_version": revised.version,
            "confirmed_at": datetime.now(UTC).isoformat(),
        },
    )

    superseded = replace(
        state,
        plan=revised,
        stage=Stage.REVIEW,
        planning_trace=[*state.planning_trace, confirmation],
        history=[
            *state.history[:-1],
            ExecutedVersion(
                plan=state.history[-1].plan.superseded(), result=state.history[-1].result
            ),
        ],
        pending_revision=None,
    )
    return approve_and_run(
        superseded,
        pipeline,
        note=f"Confirmed revision {revision.revision_id}",
        use_llm_narrative=use_llm_narrative,
    )


def reset(state: WorkflowState) -> WorkflowState:
    """Start over, keeping nothing. Used by the 'new analysis' control."""
    return WorkflowState(
        objective=state.objective,
        geographies=list(state.geographies),
        retailer_type=state.retailer_type,
        store_format=state.store_format,
        target_segments=state.target_segments,
    )


__all__ = [
    "ExecutedVersion",
    "Stage",
    "WorkflowError",
    "WorkflowState",
    "answer",
    "approve_and_run",
    "confirm_revision",
    "describe",
    "discard_revision",
    "edit",
    "propose",
    "reject",
    "reset",
]
