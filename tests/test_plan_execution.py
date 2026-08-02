"""Execution is gated on approval, and the trace records who authorized what.

These run the real pipeline against a mocked Atlas transport, so the approval gate is
tested where it actually sits rather than in isolation.
"""

from __future__ import annotations

import pytest

from models.analysis import TraceAuthority
from models.metrics import MetricCategory
from models.plan import PlanNotApprovedError, PlanStatus
from orchestration.pipeline import AnalysisPipeline
from planning.deterministic import PlanningRequest, build_deterministic_plan
from planning.planner import propose_plan
from planning.validation import validate_plan
from tests.conftest import default_builder

OBJECTIVE = (
    "Compare Burlington, South Burlington, and Winooski for a suburban apparel store "
    "targeting middle-income families. Prioritize growth and accessibility."
)
REGIONS = ["Burlington", "South Burlington", "Winooski"]


def _plan(**kwargs):
    request = PlanningRequest(objective=OBJECTIVE, geographies=list(REGIONS), **kwargs)
    return validate_plan(build_deterministic_plan(request))


def _pipeline(client_factory):
    return AnalysisPipeline(client_factory=client_factory(default_builder()))


# ------------------------------------------------------------------- the approval gate


def test_an_unapproved_plan_cannot_be_executed(client_factory):
    plan = _plan()
    assert plan.status == PlanStatus.READY_FOR_REVIEW

    with pytest.raises(PlanNotApprovedError):
        _pipeline(client_factory).run_approved(plan)


def test_a_plan_needing_clarification_cannot_be_executed(client_factory):
    plan = validate_plan(
        build_deterministic_plan(
            PlanningRequest(objective="Where should we open next?", geographies=[])
        )
    )

    with pytest.raises(PlanNotApprovedError):
        _pipeline(client_factory).run_approved(plan)


def test_a_rejected_plan_cannot_be_executed(client_factory):
    plan = _plan().rejected(note="wrong regions")

    with pytest.raises(PlanNotApprovedError):
        _pipeline(client_factory).run_approved(plan)


def test_a_forged_status_without_an_approval_record_cannot_be_executed(client_factory):
    forged = _plan().model_copy(update={"status": PlanStatus.APPROVED})

    with pytest.raises(PlanNotApprovedError):
        _pipeline(client_factory).run_approved(forged)


def test_no_atlas_call_is_made_when_execution_is_refused():
    """The gate is before the client factory, so an unapproved plan cannot reach the API."""

    def exploding_factory():
        raise AssertionError("An unapproved plan reached the Atlas client.")

    pipeline = AnalysisPipeline(client_factory=exploding_factory)

    with pytest.raises(PlanNotApprovedError):
        pipeline.run_approved(_plan())


def test_an_approved_plan_executes_and_produces_a_ranking(client_factory):
    result = _pipeline(client_factory).run_approved(_plan().approved())

    assert not result.refused
    assert result.recommendation is not None
    assert len(result.recommendation.ranked_regions) == 3
    assert result.reproducibility_hash


# ------------------------------------------------------------------- plan lineage


def test_the_executed_plan_is_carried_on_the_result(client_factory):
    plan = _plan().approved()
    result = _pipeline(client_factory).run_approved(plan)

    assert result.proposal is not None
    assert result.proposal.plan_id == plan.plan_id
    assert result.proposal.status == PlanStatus.EXECUTED
    assert result.plan_version == 1


def test_the_approved_weights_are_the_weights_that_scored(client_factory):
    plan = _plan().approved()
    result = _pipeline(client_factory).run_approved(plan)

    assert result.plan is not None
    for category, weight in plan.category_weights.items():
        assert result.plan.category_weights[category] == pytest.approx(weight)


def test_only_the_approved_metrics_are_requested(client_factory):
    plan = validate_plan(
        _plan().model_copy(
            update={
                "selected_metric_ids": [
                    "total_population",
                    "median_household_income",
                    "median_age",
                    "employment_rate",
                ]
            }
        )
    ).approved()

    result = _pipeline(client_factory).run_approved(plan)

    requested = {item.metric.metric_id for item in result.evidence.items}
    assert requested == set(plan.selected_metric_ids)


# --------------------------------------------------------------- metric weight override


def test_a_metric_weight_override_changes_the_score_and_the_hash(client_factory):
    baseline = _pipeline(client_factory).run_approved(_plan().approved())

    weighted = validate_plan(
        _plan().model_copy(update={"metric_weight_overrides": {"total_population": 5.0}})
    ).approved()
    overridden = _pipeline(client_factory).run_approved(weighted)

    assert overridden.reproducibility_hash != baseline.reproducibility_hash
    baseline_scores = {
        region.geography.slug: region.overall_score
        for region in baseline.recommendation.ranked_regions
    }
    overridden_scores = {
        region.geography.slug: region.overall_score
        for region in overridden.recommendation.ranked_regions
    }
    assert baseline_scores != overridden_scores


def test_an_override_is_disclosed_in_the_approval_trace(client_factory):
    plan = validate_plan(
        _plan().model_copy(update={"metric_weight_overrides": {"total_population": 5.0}})
    ).approved()
    result = _pipeline(client_factory).run_approved(plan)

    entry = next(e for e in result.trace if e.step == "plan_approved")
    assert entry.payload["metric_weight_overrides"] == {"total_population": 5.0}


# ------------------------------------------------------------------ the decision log


def test_the_trace_separates_who_authorized_each_step(client_factory):
    outcome = propose_plan(
        PlanningRequest(objective=OBJECTIVE, geographies=list(REGIONS))
    )
    result = _pipeline(client_factory).run_approved(
        outcome.plan.approved(), planning_trace=outcome.trace
    )

    authorities = {entry.authority for entry in result.trace}
    for expected in (
        TraceAuthority.USER,
        TraceAuthority.AGENT,
        TraceAuthority.VALIDATION,
        TraceAuthority.HUMAN_APPROVAL,
        TraceAuthority.API,
        TraceAuthority.CALCULATION,
        TraceAuthority.EXPLANATION,
    ):
        assert expected in authorities, f"no trace entry attributed to {expected}"


def test_the_trace_carries_the_original_objective_and_the_sanitized_one(client_factory):
    outcome = propose_plan(
        PlanningRequest(objective=OBJECTIVE, geographies=list(REGIONS))
    )
    result = _pipeline(client_factory).run_approved(
        outcome.plan.approved(), planning_trace=outcome.trace
    )

    original = next(e for e in result.trace if e.step == "objective_received")
    classified = next(e for e in result.trace if e.step == "classify_objective")

    assert original.payload["objective"] == OBJECTIVE
    assert classified.payload["sanitized_objective"]
    assert original.authority == TraceAuthority.USER


def test_the_trace_records_the_approval_timestamp_and_plan_version(client_factory):
    result = _pipeline(client_factory).run_approved(_plan().approved())

    entry = next(e for e in result.trace if e.step == "plan_approved")
    assert entry.authority == TraceAuthority.HUMAN_APPROVAL
    assert entry.payload["approved_at"]
    assert entry.payload["version"] == 1


def test_human_edits_made_before_approval_appear_in_the_trace(client_factory):
    from models.plan import PlanEdit

    plan = _plan()
    edited = validate_plan(
        plan.model_copy(
            update={
                "category_weights": {
                    **plan.category_weights,
                    MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.5,
                }
            }
        )
    ).approved(
        edits=[
            PlanEdit(
                field="category_weights.economic_attractiveness",
                before=plan.category_weights[MetricCategory.ECONOMIC_ATTRACTIVENESS],
                after=0.5,
            )
        ]
    )

    result = _pipeline(client_factory).run_approved(edited)
    entry = next(e for e in result.trace if e.step == "plan_approved")

    assert entry.payload["human_edits"]
    assert entry.payload["human_edits"][0]["after"] == 0.5


def test_the_planner_trace_survives_into_the_executed_result(client_factory):
    outcome = propose_plan(
        PlanningRequest(objective=OBJECTIVE, geographies=list(REGIONS))
    )
    result = _pipeline(client_factory).run_approved(
        outcome.plan.approved(), planning_trace=outcome.trace
    )

    steps = [entry.step for entry in result.trace]
    assert steps.index("objective_received") < steps.index("plan_approved")
    assert steps.index("plan_approved") < steps.index("atlas_calls")
    assert "validate_plan" in steps


# --------------------------------------------------------- 11. insufficient evidence


def test_an_approved_plan_still_obeys_the_sufficiency_gate(client_factory):
    """Approval authorizes the analysis. It does not authorize a conclusion."""
    plan = validate_plan(
        _plan().model_copy(
            update={
                "selected_metric_ids": ["total_population", "total_households"],
                "candidate_geographies": _plan().candidate_geographies[:2],
            }
        )
    ).approved()

    result = _pipeline(client_factory).run_approved(plan)

    assert result.refused
    assert result.recommendation is None
    assert result.evidence is not None
    assert result.proposal is not None
