"""Strategy profiles and deterministic sensitivity analysis.

Nothing here estimates anything. Every figure is produced by re-running the existing
scoring service over the *same* evidence package with different weights, which is cheap
because scoring is pure: no Atlas call is repeated and no value changes. What changes is
the emphasis, and the point of the exercise is to find out whether the recommendation
survives it.

The three profiles are decision lenses, not candidate truths. A growth-weighted reading
and a purchasing-power-weighted reading of the same market are both legitimate, and an
executive whose answer flips between them has learned something more useful than the
answer itself.

Asking a model to estimate sensitivity would defeat the purpose entirely, so the flip
point is found by scanning: the weight is walked across its range at a fixed resolution
and the ranking is recomputed at each step. Slower than an analytic solution and immune
to being subtly wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.evidence import EvidencePackage
from models.metrics import CATEGORY_LABELS, MetricCategory, MetricDefinition
from models.sensitivity import (
    FlipPoint,
    MetricInfluence,
    ProfileComparison,
    ProfileRanking,
    RankDelta,
    RegionScore,
    SensitivityReport,
    StrategyProfile,
)
from scoring.service import DEFAULT_CATEGORY_WEIGHTS, ScoringConfig, ScoringOutput, ScoringService

FLIP_RESOLUTION = 0.01
"""Step size for the flip-point scan, in absolute category weight."""


STRATEGY_PROFILES: tuple[StrategyProfile, ...] = (
    StrategyProfile(
        profile_id="growth_focused",
        display_name="Growth-focused",
        description=(
            "Weights the direction of the market over its current state. Growth Outlook "
            "carries the most weight, with Market Potential reduced."
        ),
        when_to_use=(
            "A long lease, or a market you expect to hold for a decade, where the "
            "trajectory over the term matters more than conditions on opening day."
        ),
        category_weights={
            MetricCategory.MARKET_POTENTIAL: 0.15,
            MetricCategory.CUSTOMER_FIT: 0.20,
            MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.15,
            MetricCategory.ACCESSIBILITY: 0.10,
            MetricCategory.GROWTH_OUTLOOK: 0.40,
        },
    ),
    StrategyProfile(
        profile_id="purchasing_power_focused",
        display_name="Purchasing-power-focused",
        description=(
            "Weights what the area can afford to spend today. Economic Attractiveness "
            "dominates, with Growth Outlook reduced."
        ),
        when_to_use=(
            "A higher price point, where the binding constraint is household budget "
            "rather than the number of households."
        ),
        category_weights={
            MetricCategory.MARKET_POTENTIAL: 0.20,
            MetricCategory.CUSTOMER_FIT: 0.15,
            MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.45,
            MetricCategory.ACCESSIBILITY: 0.10,
            MetricCategory.GROWTH_OUTLOOK: 0.10,
        },
    ),
    StrategyProfile(
        profile_id="accessibility_focused",
        display_name="Accessibility-focused",
        description=(
            "Weights how easily the catchment can reach the store. Accessibility carries "
            "the most weight, with Customer Fit reduced."
        ),
        when_to_use=(
            "A destination or drive-to format, where the catchment depends on people "
            "travelling in rather than walking past. Note that Accessibility rests on a "
            "single commute-time metric at city level, so this lens is the narrowest."
        ),
        category_weights={
            MetricCategory.MARKET_POTENTIAL: 0.20,
            MetricCategory.CUSTOMER_FIT: 0.10,
            MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.15,
            MetricCategory.ACCESSIBILITY: 0.40,
            MetricCategory.GROWTH_OUTLOOK: 0.15,
        },
    ),
)

BASELINE_PROFILE = StrategyProfile(
    profile_id="approved",
    display_name="Approved plan",
    description="The weights the executive approved for this analysis.",
    when_to_use="The reference point every other lens is compared against.",
    category_weights=dict(DEFAULT_CATEGORY_WEIGHTS),
)


def get_profile(profile_id: str) -> StrategyProfile | None:
    return next(
        (profile for profile in STRATEGY_PROFILES if profile.profile_id == profile_id),
        None,
    )


@dataclass
class ScoredProfile:
    profile: StrategyProfile
    output: ScoringOutput


def _rank(output: ScoringOutput) -> list[RegionScore]:
    return [
        RegionScore(
            slug=region.geography.slug,
            display_name=region.geography.display_name,
            rank=region.rank,
            overall_score=region.overall_score,
        )
        for region in output.ranked_regions
    ]


def score_with_profile(
    package: EvidencePackage,
    metrics: dict[str, MetricDefinition],
    profile: StrategyProfile,
) -> ScoredProfile:
    """Re-score the existing evidence under one profile's weights."""
    output = ScoringService(
        ScoringConfig(category_weights=dict(profile.category_weights))
    ).score(package, metrics)
    return ScoredProfile(profile=profile, output=output)


def _to_ranking(scored: ScoredProfile) -> ProfileRanking:
    return ProfileRanking(
        profile_id=scored.profile.profile_id,
        display_name=scored.profile.display_name,
        reproducibility_hash=scored.output.reproducibility_hash,
        regions=_rank(scored.output),
        insufficient_evidence=scored.output.insufficient_evidence,
        insufficient_reason=scored.output.insufficient_reason,
    )


def _deltas(baseline: ProfileRanking, other: ProfileRanking) -> list[RankDelta]:
    by_slug = {region.slug: region for region in baseline.regions}
    deltas: list[RankDelta] = []
    for region in other.regions:
        reference = by_slug.get(region.slug)
        if reference is None:
            continue
        deltas.append(
            RankDelta(
                slug=region.slug,
                display_name=region.display_name,
                baseline_rank=reference.rank,
                comparison_rank=region.rank,
                baseline_score=reference.overall_score,
                comparison_score=region.overall_score,
            )
        )
    return sorted(deltas, key=lambda delta: delta.comparison_rank)


def compare_profiles(
    package: EvidencePackage,
    metrics: dict[str, MetricDefinition],
    approved_weights: dict[MetricCategory, float],
    profiles: tuple[StrategyProfile, ...] = STRATEGY_PROFILES,
) -> ProfileComparison:
    """Score the same evidence under the approved weights and each alternative lens."""
    baseline_profile = BASELINE_PROFILE.model_copy(
        update={"category_weights": dict(approved_weights)}
    )
    baseline = _to_ranking(score_with_profile(package, metrics, baseline_profile))

    rankings = [_to_ranking(score_with_profile(package, metrics, p)) for p in profiles]
    deltas = {ranking.profile_id: _deltas(baseline, ranking) for ranking in rankings}

    winners = {
        ranking.winner.slug for ranking in [baseline, *rankings] if ranking.winner is not None
    }
    stable = len(winners) <= 1

    if stable and baseline.winner is not None:
        note = (
            f"{baseline.winner.display_name} leads under the approved weights and under "
            f"all {len(rankings)} alternative profiles. The recommendation is a property "
            "of the market rather than of the weighting."
        )
    elif baseline.winner is None:
        note = "No region produced a score under the approved weights."
    else:
        flipping = [
            f"{ranking.display_name} favours {ranking.winner.display_name}"
            for ranking in rankings
            if ranking.winner is not None and ranking.winner.slug != baseline.winner.slug
        ]
        note = (
            "The leader changes with the weighting, so the recommendation is sensitive to "
            "an assumption rather than settled by the evidence: "
            + "; ".join(flipping)
            + ". Which lens is right is a business judgement the data cannot make."
        )

    return ProfileComparison(
        baseline=baseline,
        profiles=rankings,
        deltas=deltas,
        stable=stable,
        stability_note=note,
    )


def metric_influences(output: ScoringOutput) -> list[MetricInfluence]:
    """Points of each region's overall score attributable to each metric.

    Read directly off the score breakdown the scoring service already produced, so this
    is a reorganization of published arithmetic rather than a new calculation.
    """
    influences: list[MetricInfluence] = []
    for region in output.ranked_regions:
        overall = region.overall_score or 0.0
        for category_score in region.category_scores:
            if category_score.score is None:
                continue
            for contribution in category_score.contributions:
                if not contribution.included or contribution.weighted_contribution is None:
                    continue
                points = (
                    category_score.effective_category_weight
                    * contribution.weighted_contribution
                )
                influences.append(
                    MetricInfluence(
                        slug=region.geography.slug,
                        display_name=region.geography.display_name,
                        metric_id=contribution.metric_id,
                        metric_name=contribution.display_name,
                        category=contribution.category,
                        normalized_value=contribution.normalized_value or 0.0,
                        contribution=round(points, 4),
                        share_of_score=round(points / overall, 4) if overall else 0.0,
                    )
                )
    return influences


def find_flip_points(
    package: EvidencePackage,
    metrics: dict[str, MetricDefinition],
    approved_weights: dict[MetricCategory, float],
    resolution: float = FLIP_RESOLUTION,
) -> list[FlipPoint]:
    """For each category, the weight at which the top two regions swap, if any.

    The scan moves one category's weight across [0, 1] while holding the *ratio* of the
    others constant, which is what an executive means by "if I cared more about income".
    Every step is a full deterministic rescore.
    """
    baseline = ScoringService(ScoringConfig(dict(approved_weights))).score(package, metrics)
    ranked = [r for r in baseline.ranked_regions if r.overall_score is not None]
    if len(ranked) < 2:
        return []

    leader, runner_up = ranked[0].geography.slug, ranked[1].geography.slug
    normalized = ScoringConfig(dict(approved_weights)).normalized()

    points: list[FlipPoint] = []
    for category in MetricCategory:
        current = normalized.get(category, 0.0)
        others = {c: w for c, w in normalized.items() if c != category}
        others_total = sum(others.values())

        found: float | None = None
        steps = int(round(1.0 / resolution))
        for step in range(steps + 1):
            candidate = round(step * resolution, 6)
            if abs(candidate - current) < resolution / 2:
                continue
            if others_total > 0:
                scaled = {
                    c: w / others_total * (1.0 - candidate) for c, w in others.items()
                }
            else:
                scaled = {c: (1.0 - candidate) / max(1, len(others)) for c in others}
            weights = {category: candidate, **scaled}
            if sum(weights.values()) <= 0:
                continue

            output = ScoringService(ScoringConfig(weights)).score(package, metrics)
            scored = [r for r in output.ranked_regions if r.overall_score is not None]
            if len(scored) < 2:
                continue
            if scored[0].geography.slug == runner_up:
                # Nearest flip to the current weight is the informative one.
                if found is None or abs(candidate - current) < abs(found - current):
                    found = candidate

        label = CATEGORY_LABELS[category]
        if found is None:
            points.append(
                FlipPoint(
                    category=category,
                    current_weight=round(current, 4),
                    flips=False,
                    note=(
                        f"Moving {label} anywhere between 0% and 100% does not put "
                        f"{ranked[1].geography.display_name} ahead of "
                        f"{ranked[0].geography.display_name}. The leader does not depend "
                        "on this category."
                    ),
                )
            )
        else:
            direction = "increased" if found > current else "reduced"
            points.append(
                FlipPoint(
                    category=category,
                    current_weight=round(current, 4),
                    flips=True,
                    required_weight=round(found, 4),
                    direction=direction,
                    note=(
                        f"{label} would have to be {direction} from {current:.0%} to about "
                        f"{found:.0%} before {ranked[1].geography.display_name} overtakes "
                        f"{ranked[0].geography.display_name}."
                    ),
                )
            )
    return points


def build_sensitivity_report(
    package: EvidencePackage,
    metrics: dict[str, MetricDefinition],
    approved_weights: dict[MetricCategory, float],
    include_flip_points: bool = True,
    resolution: float = FLIP_RESOLUTION,
) -> SensitivityReport:
    """The full deterministic sensitivity picture for one executed analysis."""
    comparison = compare_profiles(package, metrics, approved_weights)
    baseline_output = ScoringService(ScoringConfig(dict(approved_weights))).score(
        package, metrics
    )
    return SensitivityReport(
        comparison=comparison,
        influences=metric_influences(baseline_output),
        flip_points=(
            find_flip_points(package, metrics, approved_weights, resolution)
            if include_flip_points
            else []
        ),
        resolution=resolution,
    )
