"""The plan object's own guarantees.

These are the invariants everything else in the planning layer relies on: an unvalidated
plan cannot be approved, an unapproved plan cannot be executed, and an unknown never
silently becomes an assumption.
"""

from __future__ import annotations

import pytest

from models.geography import Geography
from models.metrics import MetricCategory
from models.plan import (
    AnalysisPlanProposal,
    ApprovalRecord,
    ClarificationQuestion,
    PlanCheck,
    PlanNotApprovableError,
    PlanStatus,
    PlanValidationReport,
    PlanValidationStatus,
)
from models.strategy import Attributed, Provenance, RetailStrategyProfile

BURLINGTON = Geography.parse("city:burlington-vt")
WINOOSKI = Geography.parse("city:winooski-vt")


def _passing_validation() -> PlanValidationReport:
    return PlanValidationReport(
        status=PlanValidationStatus.PASSED,
        checks=[PlanCheck(name="geographies", passed=True, detail="two resolved")],
    )


def _ready_plan(**overrides) -> AnalysisPlanProposal:
    defaults = dict(
        candidate_geographies=[BURLINGTON, WINOOSKI],
        selected_metric_ids=["total_population", "median_household_income"],
        category_weights={MetricCategory.MARKET_POTENTIAL: 1.0},
        status=PlanStatus.READY_FOR_REVIEW,
        validation=_passing_validation(),
    )
    defaults.update(overrides)
    return AnalysisPlanProposal(**defaults)


# ------------------------------------------------------------------- approval gating


def test_a_plan_that_has_not_been_validated_cannot_be_approved():
    plan = AnalysisPlanProposal(candidate_geographies=[BURLINGTON, WINOOSKI])

    assert not plan.can_approve
    with pytest.raises(PlanNotApprovableError):
        plan.approved()


def test_a_plan_that_failed_validation_cannot_be_approved():
    plan = _ready_plan(
        validation=PlanValidationReport(
            status=PlanValidationStatus.FAILED,
            checks=[
                PlanCheck(name="geographies", passed=False, detail="only one resolved")
            ],
        )
    )

    assert not plan.can_approve
    with pytest.raises(PlanNotApprovableError) as caught:
        plan.approved()
    assert "geographies" in str(caught.value)


def test_an_unanswered_required_question_blocks_approval():
    plan = _ready_plan(
        clarification_questions=[
            ClarificationQuestion(
                question_id="format",
                question="Outlet or full-price?",
                missing_decision="store format",
                why_it_matters="It changes the income weighting.",
                required=True,
            )
        ]
    )

    assert plan.unanswered_required_questions
    assert not plan.can_approve

    answered = plan.answered({"format": "full-price"})
    assert not answered.unanswered_required_questions
    assert answered.can_approve


def test_an_unanswered_optional_question_does_not_block_approval():
    plan = _ready_plan(
        clarification_questions=[
            ClarificationQuestion(
                question_id="trade_area",
                question="Municipality or drive time?",
                missing_decision="trade-area definition",
                why_it_matters="It changes how the region is interpreted.",
                required=False,
                safe_default="Treat each municipality as the market.",
            )
        ]
    )

    assert plan.can_approve


def test_a_blank_answer_does_not_count_as_answered():
    plan = _ready_plan(
        clarification_questions=[
            ClarificationQuestion(
                question_id="format",
                question="Outlet or full-price?",
                missing_decision="store format",
                why_it_matters="It changes the income weighting.",
                required=True,
            )
        ]
    ).answered({"format": "   "})

    assert plan.unanswered_required_questions


# ------------------------------------------------------------------ execution gating


def test_only_an_approved_plan_can_execute():
    plan = _ready_plan()
    assert not plan.can_execute

    approved = plan.approved()
    assert approved.status == PlanStatus.APPROVED
    assert approved.can_execute
    assert approved.approval_record.approved_at is not None


def test_forging_the_status_without_an_approval_record_does_not_grant_execution():
    """Status alone is not authority; the approval record has to be there too."""
    plan = _ready_plan().model_copy(update={"status": PlanStatus.APPROVED})

    assert plan.approval_record.approved is False
    assert not plan.can_execute


def test_forging_the_approval_record_without_validation_does_not_grant_execution():
    plan = _ready_plan(
        validation=PlanValidationReport(status=PlanValidationStatus.FAILED)
    ).model_copy(
        update={
            "status": PlanStatus.APPROVED,
            "approval_record": ApprovalRecord.approve(),
        }
    )

    assert not plan.can_execute


def test_rejection_and_supersession_are_recorded_rather_than_deleting_the_plan():
    plan = _ready_plan().approved()

    superseded = plan.superseded()
    assert superseded.status == PlanStatus.SUPERSEDED
    assert superseded.plan_id == plan.plan_id
    # The original object is untouched, so a prior result stays comparable.
    assert plan.status == PlanStatus.APPROVED

    rejected = _ready_plan().rejected(note="wrong regions")
    assert rejected.status == PlanStatus.REJECTED
    assert rejected.approval_record.approved is False


# ------------------------------------------------------------------- plan contents


def test_a_proposal_carries_no_atlas_identifier_or_factual_value():
    """The proposal names metric ids, never datapoints, and holds no observed number."""
    plan = _ready_plan()
    serialized = plan.model_dump_json()

    assert "dem.acs" not in serialized
    assert "total_population" in serialized


def test_a_revision_child_points_at_its_parent_and_bumps_the_version():
    parent = _ready_plan().approved()
    child = parent.model_copy(
        update={
            "version": parent.version + 1,
            "parent_plan_id": parent.plan_id,
            "revision_summary": "Doubled income weight",
            "status": PlanStatus.READY_FOR_REVIEW,
            "approval_record": ApprovalRecord(),
        }
    )

    assert child.parent_plan_id == parent.plan_id
    assert child.version == 2
    assert not child.can_execute


# --------------------------------------------------------------------- provenance


def test_an_unknown_field_is_not_an_assumption():
    profile = RetailStrategyProfile(
        retailer_type=Attributed[str].from_user("apparel"),
        store_format=Attributed[str].unknown("Materially changes the income weighting."),
        strategic_priorities=Attributed[list[str]].inferred(
            ["growth"], "Read from 'prioritize growth' in the objective."
        ),
    )

    assert "store_format" in profile.unknowns()
    assert "store_format" not in profile.assumptions()
    assert "strategic_priorities" in profile.assumptions()
    assert profile.retailer_type.provenance == Provenance.USER_SUPPLIED
    assert not profile.store_format.is_known


def test_an_inferred_value_always_carries_its_basis():
    inferred = Attributed[str].inferred("suburban", "The objective said 'suburban'.")

    assert inferred.is_assumption
    assert inferred.note


def test_an_unsupported_dimension_is_distinguished_from_an_unknown_one():
    profile = RetailStrategyProfile(
        requested_dimensions=Attributed[list[str]].unsupported(
            ["low rent"], "Atlas carries no property-cost data."
        )
    )

    assert "requested_dimensions" in profile.unsupported()
    assert "requested_dimensions" not in profile.unknowns()
