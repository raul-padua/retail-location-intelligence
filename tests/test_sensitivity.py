"""Strategy profiles, weight sensitivity, and version comparison.

All of it re-runs the deterministic scorer over an already-retrieved evidence package, so
no test here touches the network and no figure is estimated.
"""

from __future__ import annotations

import pytest

from models.metrics import MetricCategory
from orchestration.comparison import diff_plans, diff_results
from orchestration.pipeline import AnalysisPipeline
from planning.deterministic import PlanningRequest, build_deterministic_plan
from planning.validation import validate_plan
from scoring.sensitivity import (
    STRATEGY_PROFILES,
    build_sensitivity_report,
    compare_profiles,
    find_flip_points,
    get_profile,
    metric_influences,
    score_with_profile,
)
from scoring.service import ScoringConfig, ScoringService
from tests.conftest import default_builder

REGIONS = ["Burlington", "South Burlington", "Winooski", "Williston"]


@pytest.fixture
def executed(client_factory):
    plan = validate_plan(
        build_deterministic_plan(
            PlanningRequest(objective="Compare these markets", geographies=list(REGIONS))
        )
    ).approved()
    pipeline = AnalysisPipeline(client_factory=client_factory(default_builder()))
    result = pipeline.run_approved(plan)
    metrics = pipeline._metrics_for_scoring(plan.selected_metric_ids, None)
    return result, plan, metrics


# ------------------------------------------------------------------- 8. the profiles


def test_three_profiles_are_defined_with_explicit_weights():
    assert len(STRATEGY_PROFILES) == 3
    ids = {profile.profile_id for profile in STRATEGY_PROFILES}
    assert ids == {"growth_focused", "purchasing_power_focused", "accessibility_focused"}

    for profile in STRATEGY_PROFILES:
        assert sum(profile.category_weights.values()) == pytest.approx(1.0)
        assert set(profile.category_weights) == set(MetricCategory)
        assert profile.when_to_use


def test_each_profile_leans_on_the_category_it_is_named_for():
    emphasis = {
        "growth_focused": MetricCategory.GROWTH_OUTLOOK,
        "purchasing_power_focused": MetricCategory.ECONOMIC_ATTRACTIVENESS,
        "accessibility_focused": MetricCategory.ACCESSIBILITY,
    }
    for profile_id, category in emphasis.items():
        profile = get_profile(profile_id)
        weights = profile.category_weights
        assert weights[category] == max(weights.values())


def test_each_profile_produces_its_own_reproducibility_hash(executed):
    result, plan, metrics = executed

    hashes = {
        profile.profile_id: score_with_profile(
            result.evidence, metrics, profile
        ).output.reproducibility_hash
        for profile in STRATEGY_PROFILES
    }

    assert len(set(hashes.values())) == len(hashes)
    assert result.reproducibility_hash not in set(hashes.values())


def test_a_profile_rerun_is_reproducible(executed):
    result, _, metrics = executed
    profile = get_profile("growth_focused")

    first = score_with_profile(result.evidence, metrics, profile).output
    second = score_with_profile(result.evidence, metrics, profile).output

    assert first.reproducibility_hash == second.reproducibility_hash
    assert [r.geography.slug for r in first.ranked_regions] == [
        r.geography.slug for r in second.ranked_regions
    ]


def test_profiles_use_only_approved_metrics(executed, registry):
    result, plan, metrics = executed

    for metric_id in metrics:
        assert registry.get(metric_id) is not None


def test_the_comparison_reports_ranking_stability(executed):
    result, plan, metrics = executed

    comparison = compare_profiles(result.evidence, metrics, plan.category_weights)

    assert comparison.baseline.regions
    assert len(comparison.profiles) == 3
    assert comparison.stability_note
    assert isinstance(comparison.stable, bool)
    if comparison.stable:
        assert "property of the market" in comparison.stability_note
    else:
        assert "sensitive to" in comparison.stability_note


def test_the_comparison_reports_rank_and_score_deltas(executed):
    result, plan, metrics = executed

    comparison = compare_profiles(result.evidence, metrics, plan.category_weights)
    deltas = comparison.deltas["growth_focused"]

    assert len(deltas) == len(comparison.baseline.regions)
    for delta in deltas:
        assert delta.score_change is not None
        # A positive rank_change means the region climbed.
        assert delta.rank_change == delta.baseline_rank - delta.comparison_rank


def test_a_profile_is_presented_as_a_lens_not_a_correct_model():
    for profile in STRATEGY_PROFILES:
        assert profile.description
        assert profile.when_to_use
        assert "correct" not in profile.description.lower()


# ------------------------------------------------------------------ metric influence


def test_metric_influence_decomposes_the_score_it_came_from(executed):
    result, plan, metrics = executed
    output = ScoringService(ScoringConfig(dict(plan.category_weights))).score(
        result.evidence, metrics
    )

    influences = metric_influences(output)
    assert influences

    for region in output.ranked_regions:
        if region.overall_score is None:
            continue
        total = sum(
            entry.contribution for entry in influences if entry.slug == region.geography.slug
        )
        assert total == pytest.approx(region.overall_score, abs=0.05)


def test_influence_can_be_read_per_region(executed):
    result, plan, metrics = executed
    report = build_sensitivity_report(
        result.evidence, metrics, plan.category_weights, include_flip_points=False
    )

    leader = report.comparison.baseline.winner
    top = report.influences_for(leader.slug)

    assert top
    assert top[0].contribution >= top[-1].contribution


# --------------------------------------------------------------------- flip points


def test_the_flip_point_scan_is_deterministic_and_covers_every_category(executed):
    result, plan, metrics = executed

    first = find_flip_points(result.evidence, metrics, plan.category_weights, resolution=0.05)
    second = find_flip_points(result.evidence, metrics, plan.category_weights, resolution=0.05)

    assert len(first) == len(MetricCategory)
    assert [point.model_dump() for point in first] == [
        point.model_dump() for point in second
    ]


def test_a_reported_flip_point_actually_flips_the_ranking(executed):
    """The claim is checked by rescoring at the reported weight."""
    result, plan, metrics = executed
    normalized = ScoringConfig(dict(plan.category_weights)).normalized()

    baseline = ScoringService(ScoringConfig(dict(plan.category_weights))).score(
        result.evidence, metrics
    )
    runner_up = baseline.ranked_regions[1].geography.slug

    points = find_flip_points(result.evidence, metrics, plan.category_weights, resolution=0.05)
    flipping = [point for point in points if point.flips]

    for point in flipping:
        others = {c: w for c, w in normalized.items() if c != point.category}
        others_total = sum(others.values())
        weights = {
            point.category: point.required_weight,
            **{
                c: w / others_total * (1.0 - point.required_weight)
                for c, w in others.items()
            },
        }
        rescored = ScoringService(ScoringConfig(weights)).score(result.evidence, metrics)
        assert rescored.ranked_regions[0].geography.slug == runner_up


def test_a_category_that_cannot_flip_the_result_says_so(executed):
    result, plan, metrics = executed

    points = find_flip_points(result.evidence, metrics, plan.category_weights, resolution=0.05)

    for point in points:
        if not point.flips:
            assert "does not depend on this category" in point.note
            assert point.required_weight is None


def test_the_full_report_flags_assumption_sensitivity(executed):
    result, plan, metrics = executed

    report = build_sensitivity_report(
        result.evidence, metrics, plan.category_weights, resolution=0.1
    )

    assert report.comparison
    assert report.influences
    assert report.flip_points
    assert report.recommendation_is_assumption_sensitive is not report.comparison.stable


# ------------------------------------------------------------- 11. plan and result diff


def test_a_weight_change_is_reported_as_a_plan_diff(client_factory):
    base_plan = validate_plan(
        build_deterministic_plan(
            PlanningRequest(objective="Compare", geographies=list(REGIONS))
        )
    )
    revised = validate_plan(
        base_plan.model_copy(
            update={
                "version": 2,
                "parent_plan_id": base_plan.plan_id,
                "revision_summary": "Doubled the weight on income",
                "category_weights": {
                    **base_plan.category_weights,
                    MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.6,
                },
            }
        )
    )

    diff = diff_plans(base_plan, revised)

    assert not diff.is_empty
    assert diff.to_version == 2
    changed = {change.category for change in diff.weight_changes}
    assert MetricCategory.ECONOMIC_ATTRACTIVENESS in changed
    assert diff.revision_summary == "Doubled the weight on income"


def test_added_and_removed_metrics_are_both_reported(client_factory):
    base_plan = validate_plan(
        build_deterministic_plan(
            PlanningRequest(objective="Compare", geographies=list(REGIONS))
        )
    )
    revised = base_plan.model_copy(
        update={
            "version": 2,
            "selected_metric_ids": [
                metric_id
                for metric_id in base_plan.selected_metric_ids
                if metric_id != "median_age"
            ],
        }
    )

    diff = diff_plans(base_plan, revised)

    assert "median_age" in diff.metrics_removed
    assert not diff.metrics_added


def test_two_executed_versions_produce_a_result_diff(client_factory):
    pipeline = AnalysisPipeline(client_factory=client_factory(default_builder()))

    first_plan = validate_plan(
        build_deterministic_plan(
            PlanningRequest(objective="Compare", geographies=list(REGIONS))
        )
    ).approved()
    first = pipeline.run_approved(first_plan)

    second_plan = validate_plan(
        first_plan.model_copy(
            update={
                "version": 2,
                "parent_plan_id": first_plan.plan_id,
                "revision_summary": "Weight income far more heavily",
                "category_weights": {
                    MetricCategory.MARKET_POTENTIAL: 0.1,
                    MetricCategory.CUSTOMER_FIT: 0.1,
                    MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.6,
                    MetricCategory.ACCESSIBILITY: 0.1,
                    MetricCategory.GROWTH_OUTLOOK: 0.1,
                },
            }
        )
    ).approved()
    second = pipeline.run_approved(second_plan)

    diff = diff_results(first, second)

    assert diff.previous_hash != diff.new_hash
    assert diff.deltas
    assert any("Economic Attractiveness" in line for line in diff.attribution)
    assert not diff.evidence_changed
    assert any("change of emphasis rather than a change of fact" in line for line in diff.attribution)


def test_the_diff_does_not_claim_a_causal_magnitude(client_factory):
    """It says what changed and what moved. It does not apportion blame numerically."""
    pipeline = AnalysisPipeline(client_factory=client_factory(default_builder()))

    first_plan = validate_plan(
        build_deterministic_plan(
            PlanningRequest(objective="Compare", geographies=list(REGIONS))
        )
    ).approved()
    first = pipeline.run_approved(first_plan)
    second_plan = validate_plan(
        first_plan.model_copy(
            update={
                "version": 2,
                "category_weights": {
                    MetricCategory.MARKET_POTENTIAL: 0.1,
                    MetricCategory.CUSTOMER_FIT: 0.1,
                    MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.6,
                    MetricCategory.ACCESSIBILITY: 0.1,
                    MetricCategory.GROWTH_OUTLOOK: 0.1,
                },
            }
        )
    ).approved()
    second = pipeline.run_approved(second_plan)

    diff = diff_results(first, second)

    joined = " ".join(diff.attribution).lower()
    assert "because" not in joined
    assert "caused" not in joined


def test_the_previous_result_remains_available_after_a_rerun(client_factory):
    pipeline = AnalysisPipeline(client_factory=client_factory(default_builder()))
    plan = validate_plan(
        build_deterministic_plan(
            PlanningRequest(objective="Compare", geographies=list(REGIONS))
        )
    ).approved()

    first = pipeline.run_approved(plan)
    second = pipeline.run_approved(plan)

    assert first.reproducibility_hash == second.reproducibility_hash
    assert first.recommendation is not None
    assert first.proposal.plan_id == second.proposal.plan_id
