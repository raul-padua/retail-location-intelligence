"""The deterministic planner, the capability registry, and the plan validation gate.

Every test here runs with no LLM key configured, which is the point: the planning
experience is a product feature, not a feature of having an API key.
"""

from __future__ import annotations

import pytest

from models.capabilities import CapabilityStatus
from models.metrics import MetricCategory
from models.plan import AnalysisPlanProposal, PlanStatus, PlanValidationStatus
from models.strategy import Provenance
from planning.capabilities import get_capability_registry
from planning.deterministic import (
    DEPRIORITY_FACTOR,
    MAX_QUESTIONS_PER_ROUND,
    PRIORITY_BOOST,
    PlanningRequest,
    build_deterministic_plan,
    read_priorities,
)
from planning.validation import validate_plan
from scoring.service import DEFAULT_CATEGORY_WEIGHTS

EXPLICIT_STRATEGY = (
    "We are evaluating Burlington, South Burlington, and Winooski for a suburban apparel "
    "store targeting middle-income families. Prioritize growth and accessibility over "
    "current market size."
)


def plan_for(objective: str, geographies: list[str], **kwargs) -> AnalysisPlanProposal:
    request = PlanningRequest(objective=objective, geographies=geographies, **kwargs)
    return validate_plan(build_deterministic_plan(request))


# ------------------------------------------------------------- 1. an explicit strategy


@pytest.fixture
def explicit_plan() -> AnalysisPlanProposal:
    return plan_for(
        EXPLICIT_STRATEGY,
        ["Burlington", "South Burlington", "Winooski"],
    )


def test_an_explicit_strategy_produces_a_structured_profile(explicit_plan):
    profile = explicit_plan.retail_strategy_profile

    assert profile.store_format.value == "suburban"
    assert profile.store_format.provenance == Provenance.PLANNER_INFERRED
    assert "middle-income families" in profile.target_customer_segments.value
    assert profile.target_customer_segments.provenance == Provenance.USER_SUPPLIED


def test_an_explicit_strategy_selects_only_registry_metrics(explicit_plan, registry):
    assert explicit_plan.selected_metric_ids
    for metric_id in explicit_plan.selected_metric_ids:
        assert registry.get(metric_id) is not None


def test_named_priorities_are_weighted_above_the_defaults(explicit_plan):
    weights = explicit_plan.category_weights

    assert weights[MetricCategory.GROWTH_OUTLOOK] > DEFAULT_CATEGORY_WEIGHTS[
        MetricCategory.GROWTH_OUTLOOK
    ]
    assert weights[MetricCategory.ACCESSIBILITY] > DEFAULT_CATEGORY_WEIGHTS[
        MetricCategory.ACCESSIBILITY
    ]
    # "over current market size" demotes market potential below its own default.
    assert weights[MetricCategory.MARKET_POTENTIAL] < DEFAULT_CATEGORY_WEIGHTS[
        MetricCategory.MARKET_POTENTIAL
    ]
    assert weights[MetricCategory.GROWTH_OUTLOOK] > weights[MetricCategory.MARKET_POTENTIAL]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_describing_the_customer_is_not_a_statement_of_priority(explicit_plan):
    """"Middle-income families" says who the store is for, not what to weight.

    Reading it as emphasis would raise Customer Fit and Economic Attractiveness off a
    description and drown out the one priority the objective actually stated.
    """
    weights = explicit_plan.category_weights

    assert weights[MetricCategory.CUSTOMER_FIT] == pytest.approx(
        DEFAULT_CATEGORY_WEIGHTS[MetricCategory.CUSTOMER_FIT]
        / sum(
            DEFAULT_CATEGORY_WEIGHTS[category] * factor
            for category, factor in _explicit_factors().items()
        )
    )
    assert weights[MetricCategory.GROWTH_OUTLOOK] > weights[MetricCategory.CUSTOMER_FIT]
    assert weights[MetricCategory.ACCESSIBILITY] > DEFAULT_CATEGORY_WEIGHTS[
        MetricCategory.ACCESSIBILITY
    ]


def _explicit_factors() -> dict[MetricCategory, float]:
    """The boost/deprioritize factors EXPLICIT_STRATEGY should produce, category by category."""
    return {
        MetricCategory.MARKET_POTENTIAL: DEPRIORITY_FACTOR,
        MetricCategory.CUSTOMER_FIT: 1.0,
        MetricCategory.ECONOMIC_ATTRACTIVENESS: 1.0,
        MetricCategory.ACCESSIBILITY: PRIORITY_BOOST,
        MetricCategory.GROWTH_OUTLOOK: PRIORITY_BOOST,
    }


@pytest.mark.parametrize(
    ("objective", "raised", "lowered"),
    [
        (
            "Prioritize growth and accessibility over current market size.",
            {MetricCategory.GROWTH_OUTLOOK, MetricCategory.ACCESSIBILITY},
            {MetricCategory.MARKET_POTENTIAL},
        ),
        (
            "Purchasing power is the priority; growth matters less.",
            {MetricCategory.ECONOMIC_ATTRACTIVENESS},
            {MetricCategory.GROWTH_OUTLOOK},
        ),
        (
            "Focus on accessibility. We are less concerned about growth.",
            {MetricCategory.ACCESSIBILITY},
            {MetricCategory.GROWTH_OUTLOOK},
        ),
        (
            "Students and young adults matter most.",
            {MetricCategory.CUSTOMER_FIT},
            set(),
        ),
    ],
)
def test_priority_markers_are_read_in_both_directions(objective, raised, lowered):
    """"Prioritize X" names the category after the marker; "X is the priority" before it."""
    reading = read_priorities(objective)

    assert set(reading.priorities) == raised
    assert set(reading.secondary) == lowered


def test_an_objective_with_no_priority_marker_reads_the_whole_thing():
    """Nothing was ranked, so everything the user mentioned counts as emphasis."""
    reading = read_priorities(
        "Compare these cities for a store serving families with strong household income."
    )

    assert MetricCategory.CUSTOMER_FIT in reading.priorities
    assert MetricCategory.ECONOMIC_ATTRACTIVENESS in reading.priorities
    assert not reading.secondary


def test_the_weighting_rule_is_the_documented_one():
    """Boost, demote, renormalize. Nothing learned, nothing tuned."""
    reading = read_priorities("prioritize growth over market size")
    from planning.deterministic import weights_for

    weights, notes = weights_for(reading)

    raw = dict(DEFAULT_CATEGORY_WEIGHTS)
    raw[MetricCategory.GROWTH_OUTLOOK] *= PRIORITY_BOOST
    raw[MetricCategory.MARKET_POTENTIAL] *= DEPRIORITY_FACTOR
    total = sum(raw.values())

    for category, weight in weights.items():
        assert weight == pytest.approx(raw[category] / total)
    assert any("raised" in note for note in notes)
    assert any("lowered" in note for note in notes)


def test_an_explicit_strategy_waits_for_approval_rather_than_executing(explicit_plan):
    assert explicit_plan.status == PlanStatus.READY_FOR_REVIEW
    assert explicit_plan.can_approve
    assert not explicit_plan.can_execute


def test_the_plan_states_what_it_will_produce_and_what_evidence_it_requires(explicit_plan):
    assert explicit_plan.expected_outputs
    assert any("reproducibility hash" in output for output in explicit_plan.expected_outputs)
    assert any(
        "nothing is estimated" in requirement
        for requirement in explicit_plan.evidence_requirements
    )


def test_the_planner_says_it_was_deterministic(explicit_plan):
    assert explicit_plan.planner_provenance.is_deterministic
    assert "no language model" in explicit_plan.planner_rationale


# ---------------------------------------------------------------- 2. ambiguous request


def test_an_ambiguous_request_asks_rather_than_assuming():
    plan = plan_for("Where should we put our next store?", [])

    assert plan.status == PlanStatus.NEEDS_CLARIFICATION
    assert not plan.can_approve
    assert not plan.can_execute

    required = [q.question_id for q in plan.unanswered_required_questions]
    assert "candidate_regions" in required


def test_an_ambiguous_request_invents_no_geography_and_no_retailer_fact():
    plan = plan_for("Where should we put our next store?", [])

    assert plan.candidate_geographies == []
    profile = plan.retail_strategy_profile
    assert profile.store_format.provenance == Provenance.UNKNOWN
    assert profile.target_customer_segments.provenance == Provenance.UNKNOWN


def test_no_more_than_three_questions_are_asked_at_once():
    plan = plan_for("Where should we put our next store?", [])

    assert len(plan.clarification_questions) <= MAX_QUESTIONS_PER_ROUND


def test_answering_a_required_question_unblocks_the_plan():
    blocked = plan_for("Where should we put our next store?", [])
    assert not blocked.can_approve

    answered = plan_for(
        "Where should we put our next store?",
        ["Burlington", "Winooski"],
    )
    assert answered.can_approve


def test_an_optional_question_left_unanswered_becomes_a_disclosed_assumption():
    plan = plan_for("Compare these two markets", ["Burlington", "Winooski"])

    optional = [q for q in plan.clarification_questions if not q.required]
    assert optional
    for question in optional:
        assert question.safe_default
        assert any(
            question.safe_default == assumption.assumption for assumption in plan.assumptions
        )
    assert plan.can_approve


# ----------------------------------------------------------- 3. unsupported data request


def test_unsupported_dimensions_are_named_not_approximated():
    plan = plan_for(
        "Prioritize low rent, high foot traffic, and limited competition nearby.",
        ["Burlington", "Winooski"],
    )

    requirements = {entry.requirement for entry in plan.unsupported_requirements}
    assert "site-level lease and occupancy costs" in requirements
    assert "pedestrian or vehicle counts at candidate sites" in requirements
    assert "competitor store locations and formats" in requirements


def test_each_unsupported_dimension_names_a_future_data_source():
    plan = plan_for(
        "Prioritize low rent and high foot traffic.", ["Burlington", "Winooski"]
    )

    for requirement in plan.unsupported_requirements:
        assert requirement.why_unavailable
        assert requirement.would_require
        assert requirement.capability_id is not None


def test_an_unsupported_request_still_offers_the_atlas_comparison():
    plan = plan_for(
        "Prioritize low rent and high foot traffic.", ["Burlington", "Winooski"]
    )

    assert plan.selected_metric_ids
    assert plan.can_approve
    assert plan.retail_strategy_profile.requested_dimensions.provenance == (
        Provenance.UNSUPPORTED
    )


def test_no_proxy_metric_is_substituted_for_an_unsupported_dimension(registry):
    """Foot traffic must not quietly become 'food service establishments'."""
    with_request = plan_for(
        "Prioritize high foot traffic.", ["Burlington", "Winooski"]
    )
    without_request = plan_for("Compare these markets.", ["Burlington", "Winooski"])

    assert with_request.selected_metric_ids == without_request.selected_metric_ids


# -------------------------------------------------------------- 5. invalid weights


def test_a_negative_weight_is_rejected_rather_than_clamped():
    plan = build_deterministic_plan(
        PlanningRequest(
            objective="Compare these",
            geographies=["Burlington", "Winooski"],
            category_weights={
                MetricCategory.MARKET_POTENTIAL: -1.0,
                MetricCategory.GROWTH_OUTLOOK: 0.5,
            },
        )
    )
    validated = validate_plan(plan)

    assert validated.validation.status == PlanValidationStatus.FAILED
    assert not validated.can_approve
    detail = " ".join(check.detail for check in validated.validation.failures)
    assert "negative" in detail


def test_weights_that_do_not_sum_to_one_are_renormalized_and_disclosed():
    plan = build_deterministic_plan(
        PlanningRequest(
            objective="Compare these",
            geographies=["Burlington", "Winooski"],
            category_weights={
                MetricCategory.MARKET_POTENTIAL: 3.0,
                MetricCategory.GROWTH_OUTLOOK: 1.0,
            },
        )
    )
    validated = validate_plan(plan)

    assert validated.validation.passed
    assert sum(validated.category_weights.values()) == pytest.approx(1.0)
    assert validated.category_weights[MetricCategory.MARKET_POTENTIAL] == pytest.approx(0.75)

    disclosures = " ".join(validated.validation.disclosures)
    assert "renormalized proportionally" in disclosures
    # The categories that were left out are disclosed as zero, not quietly defaulted.
    assert "set to zero" in disclosures


def test_all_zero_weights_are_rejected():
    plan = build_deterministic_plan(
        PlanningRequest(
            objective="Compare these",
            geographies=["Burlington", "Winooski"],
            category_weights={category: 0.0 for category in MetricCategory},
        )
    )
    validated = validate_plan(plan)

    assert not validated.validation.passed


def test_a_weight_override_for_an_unknown_metric_is_rejected():
    plan = build_deterministic_plan(
        PlanningRequest(objective="Compare", geographies=["Burlington", "Winooski"])
    ).model_copy(update={"metric_weight_overrides": {"invented_metric": 2.0}})

    validated = validate_plan(plan)

    assert not validated.validation.passed


def test_a_valid_weight_override_is_accepted_and_disclosed():
    plan = build_deterministic_plan(
        PlanningRequest(objective="Compare", geographies=["Burlington", "Winooski"])
    ).model_copy(update={"metric_weight_overrides": {"total_population": 0.8}})

    validated = validate_plan(plan)

    assert validated.validation.passed
    assert any(
        "Total Population" in disclosure for disclosure in validated.validation.disclosures
    )


# ------------------------------------------------------------- validation gate itself


def test_a_metric_outside_the_registry_fails_validation():
    plan = build_deterministic_plan(
        PlanningRequest(objective="Compare", geographies=["Burlington", "Winooski"])
    ).model_copy(update={"selected_metric_ids": ["total_population", "median_rent"]})

    validated = validate_plan(plan)

    assert not validated.validation.passed
    assert "median_rent" in " ".join(
        check.detail for check in validated.validation.failures
    )


def test_an_atlas_datapoint_supplied_as_a_metric_id_fails_validation():
    """The identifier namespace and the metric namespace are deliberately separate."""
    plan = build_deterministic_plan(
        PlanningRequest(objective="Compare", geographies=["Burlington", "Winooski"])
    ).model_copy(update={"selected_metric_ids": ["dem.acs.pop.total.val"]})

    validated = validate_plan(plan)

    assert not validated.validation.passed


def test_a_single_region_fails_validation():
    plan = build_deterministic_plan(
        PlanningRequest(objective="Compare", geographies=["Burlington"])
    )
    validated = validate_plan(plan)

    assert not validated.validation.passed
    assert any(
        check.name == "candidate_geographies" for check in validated.validation.failures
    )


def test_regions_outside_the_licensed_footprint_are_reported_not_silently_dropped():
    plan = plan_for("Compare these", ["Burlington", "Winooski", "Boston, MA"])

    assert any("Boston" in entry for entry in plan.excluded_requirements)
    assert len(plan.candidate_geographies) == 2


def test_mixed_levels_with_no_common_metric_fails_before_any_api_call(registry):
    plan = build_deterministic_plan(
        PlanningRequest(objective="Compare", geographies=["Burlington", "Winooski"])
    ).model_copy(update={"selected_metric_ids": ["retail_establishments"]})

    validated = validate_plan(plan)

    assert not validated.validation.passed
    assert any(
        check.name == "metric_geography_support" for check in validated.validation.failures
    )


# ------------------------------------------------------------- capability registry


def test_the_capability_registry_separates_what_runs_from_what_does_not():
    capabilities = get_capability_registry()

    assert capabilities.available()
    assert capabilities.unavailable()
    for capability in capabilities.available():
        assert capability.status == CapabilityStatus.AVAILABLE
        assert capability.produces


def test_every_unavailable_capability_says_what_it_would_need():
    for capability in get_capability_registry().unavailable():
        assert capability.unavailable_because
        assert capability.required_data
        assert capability.expected_provider


def test_the_planner_brief_marks_unavailable_capabilities_unmistakably():
    brief = get_capability_registry().describe_for_planner()

    assert "UNAVAILABLE" in brief
    assert "never describe its output or imply it was executed" in brief


def test_unsupported_dimensions_map_onto_a_named_future_capability():
    capabilities = get_capability_registry()

    assert (
        capabilities.for_requirement("pedestrian or vehicle counts at candidate sites")
        is not None
    )
    assert capabilities.for_requirement("something nobody asked for") is None


def test_a_cannibalization_request_is_shown_as_unavailable_with_its_inputs():
    capability = get_capability_registry().get("future.cannibalization")

    assert capability is not None
    assert not capability.is_available
    assert any("store network" in entry for entry in capability.required_data)
