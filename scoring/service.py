"""Deterministic scoring service.

This module is the sole authority for every number the product reports. It contains no
model calls and no arithmetic that is not reproducible from the evidence package plus the
weight configuration, which is what the reproducibility hash attests to.

Aggregation is bottom-up and every intermediate value is retained:

    metric value -> normalized 0-100 -> weighted within its category -> category score
    category scores -> weighted by category weight -> overall score

Weights are renormalized twice, and both adjustments are disclosed:

  * within a category, over the metrics that survived validation for that region;
  * across categories, over the categories that produced a score for that region.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from models.analysis import CategoryScore, RankedRegion, ScoreBreakdown, WeightAdjustment
from models.evidence import EvidenceItem, EvidencePackage
from models.geography import Geography
from models.metrics import MetricCategory, MetricDefinition
from scoring.normalize import NormalizationResult, normalize_values

DEFAULT_CATEGORY_WEIGHTS: dict[MetricCategory, float] = {
    MetricCategory.MARKET_POTENTIAL: 0.30,
    MetricCategory.CUSTOMER_FIT: 0.25,
    MetricCategory.ECONOMIC_ATTRACTIVENESS: 0.20,
    MetricCategory.ACCESSIBILITY: 0.10,
    MetricCategory.GROWTH_OUTLOOK: 0.15,
}


@dataclass(frozen=True)
class ScoringConfig:
    category_weights: dict[MetricCategory, float] = field(
        default_factory=lambda: dict(DEFAULT_CATEGORY_WEIGHTS)
    )

    def normalized(self) -> dict[MetricCategory, float]:
        total = sum(max(0.0, weight) for weight in self.category_weights.values())
        if total <= 0:
            raise ValueError("Category weights must sum to a positive number.")
        return {
            category: max(0.0, weight) / total
            for category, weight in self.category_weights.items()
        }


@dataclass
class ScoringOutput:
    ranked_regions: list[RankedRegion]
    weight_adjustments: list[WeightAdjustment]
    normalizations: dict[str, NormalizationResult]
    """Per-metric record of the exact arithmetic applied, for the trace panel."""

    reproducibility_hash: str
    insufficient_evidence: bool
    insufficient_reason: str | None = None


class ScoringService:
    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig()

    def score(
        self,
        package: EvidencePackage,
        metrics: dict[str, MetricDefinition],
    ) -> ScoringOutput:
        geographies = package.geographies
        category_weights = self.config.normalized()

        usable = [item for item in package.items if item.is_usable]
        normalizations: dict[str, NormalizationResult] = {}
        normalized_by_metric: dict[str, dict[str, float]] = {}

        by_metric: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in usable:
            by_metric[item.metric.metric_id].append(item)

        for metric_id, items in by_metric.items():
            metric = metrics.get(metric_id) or items[0].metric
            values = {
                item.geography.slug: float(item.raw_value)
                for item in items
                if item.raw_value is not None
            }
            if len(values) < 2:
                # A metric present in a single region cannot separate candidates; the
                # validation layer normally removes these, but scoring stays defensive.
                continue
            result = normalize_values(values, metric.direction, metric.normalization)
            normalizations[metric_id] = result
            normalized_by_metric[metric_id] = result.scores

        scored_metric_ids = set(normalized_by_metric)
        adjustments: list[WeightAdjustment] = []
        for metric_id, metric in metrics.items():
            if metric_id not in scored_metric_ids:
                adjustments.append(
                    WeightAdjustment(
                        category=metric.category,
                        metric_id=metric_id,
                        original_weight=metric.weight,
                        reason=(
                            "Excluded from scoring because Atlas did not return comparable "
                            "values for at least two candidate regions. Remaining weights in "
                            f"the {metric.category} category were renormalized to sum to 1."
                        ),
                    )
                )

        ranked: list[RankedRegion] = []
        for geography in geographies:
            category_scores, missing_ids = self._score_region(
                geography, metrics, normalized_by_metric, package, category_weights
            )
            overall = self._aggregate(category_scores)
            attempted = [item for item in package.items if item.geography.slug == geography.slug]
            usable_here = [item for item in attempted if item.is_usable]
            ranked.append(
                RankedRegion(
                    geography=geography,
                    rank=0,
                    overall_score=overall,
                    category_scores=category_scores,
                    evidence_completeness=(
                        len(usable_here) / len(attempted) if attempted else 0.0
                    ),
                    missing_metric_ids=sorted(missing_ids),
                )
            )

        # Deterministic ordering: score descending, then slug ascending so that ties never
        # depend on dict iteration order.
        ranked.sort(
            key=lambda region: (
                -(region.overall_score if region.overall_score is not None else -1.0),
                region.geography.slug,
            )
        )
        for position, region in enumerate(ranked, start=1):
            ranked[position - 1] = region.model_copy(update={"rank": position})

        insufficient, reason = self._assess_sufficiency(ranked, normalized_by_metric, package)

        return ScoringOutput(
            ranked_regions=ranked,
            weight_adjustments=adjustments,
            normalizations=normalizations,
            reproducibility_hash=self._hash(package, metrics, category_weights),
            insufficient_evidence=insufficient,
            insufficient_reason=reason,
        )

    def _score_region(
        self,
        geography: Geography,
        metrics: dict[str, MetricDefinition],
        normalized_by_metric: dict[str, dict[str, float]],
        package: EvidencePackage,
        category_weights: dict[MetricCategory, float],
    ) -> tuple[list[CategoryScore], set[str]]:
        evidence_by_metric = {
            item.metric.metric_id: item
            for item in package.items
            if item.geography.slug == geography.slug
        }
        missing_ids: set[str] = set()

        by_category: dict[MetricCategory, list[MetricDefinition]] = defaultdict(list)
        for metric in metrics.values():
            by_category[metric.category].append(metric)

        category_scores: list[CategoryScore] = []
        for category in MetricCategory:
            category_metrics = sorted(by_category.get(category, []), key=lambda m: m.metric_id)
            if not category_metrics:
                continue

            included: list[tuple[MetricDefinition, float]] = []
            breakdowns: list[ScoreBreakdown] = []

            for metric in category_metrics:
                evidence = evidence_by_metric.get(metric.metric_id)
                scores = normalized_by_metric.get(metric.metric_id, {})
                normalized = scores.get(geography.slug)

                if normalized is None:
                    missing_ids.add(metric.metric_id)
                    reason = (
                        "Metric excluded from the whole comparison."
                        if metric.metric_id not in normalized_by_metric
                        else "No comparable value for this region."
                    )
                    breakdowns.append(
                        ScoreBreakdown(
                            metric_id=metric.metric_id,
                            display_name=metric.display_name,
                            category=category,
                            evidence_id=evidence.evidence_id if evidence else None,
                            raw_value=evidence.raw_value if evidence else None,
                            normalized_value=None,
                            effective_weight=0.0,
                            weighted_contribution=None,
                            included=False,
                            exclusion_reason=reason,
                        )
                    )
                else:
                    included.append((metric, normalized))
                    breakdowns.append(
                        ScoreBreakdown(
                            metric_id=metric.metric_id,
                            display_name=metric.display_name,
                            category=category,
                            evidence_id=evidence.evidence_id if evidence else None,
                            raw_value=evidence.raw_value if evidence else None,
                            normalized_value=normalized,
                            effective_weight=0.0,
                            weighted_contribution=None,
                            included=True,
                        )
                    )

            weight_total = sum(metric.weight for metric, _ in included)
            score: float | None = None
            if included and weight_total > 0:
                score = 0.0
                for metric, normalized in included:
                    effective = metric.weight / weight_total
                    contribution = effective * normalized
                    score += contribution
                    for index, breakdown in enumerate(breakdowns):
                        if breakdown.metric_id == metric.metric_id:
                            breakdowns[index] = breakdown.model_copy(
                                update={
                                    "effective_weight": round(effective, 6),
                                    "weighted_contribution": round(contribution, 4),
                                }
                            )
                score = round(score, 4)

            category_scores.append(
                CategoryScore(
                    category=category,
                    score=score,
                    category_weight=round(category_weights.get(category, 0.0), 6),
                    effective_category_weight=0.0,
                    metrics_included=len(included),
                    metrics_total=len(category_metrics),
                    contributions=breakdowns,
                )
            )

        # Renormalize category weights over the categories that actually produced a score.
        scoring_total = sum(
            entry.category_weight for entry in category_scores if entry.score is not None
        )
        for index, entry in enumerate(category_scores):
            effective = (
                entry.category_weight / scoring_total
                if entry.score is not None and scoring_total > 0
                else 0.0
            )
            category_scores[index] = entry.model_copy(
                update={"effective_category_weight": round(effective, 6)}
            )

        return category_scores, missing_ids

    @staticmethod
    def _aggregate(category_scores: list[CategoryScore]) -> float | None:
        contributing = [entry for entry in category_scores if entry.score is not None]
        if not contributing:
            return None
        total = sum(entry.effective_category_weight * entry.score for entry in contributing)
        return round(total, 4)

    MIN_METRICS_FOR_RANKING = 3
    MIN_SCORE_MARGIN = 2.0
    MIN_RAW_SEPARATION = 0.01
    """Median relative gap between the top two regions' raw values, below which the
    normalized scores are an artifact of rescaling rather than a real difference."""

    @classmethod
    def _assess_sufficiency(
        cls,
        ranked: list[RankedRegion],
        normalized_by_metric: dict[str, dict[str, float]],
        package: EvidencePackage,
    ) -> tuple[bool, str | None]:
        """Decide whether the ranking is trustworthy enough to present as a recommendation."""
        scored = [region for region in ranked if region.overall_score is not None]
        if len(scored) < 2:
            return True, (
                "Fewer than two candidate regions produced a score, so there is nothing to rank."
            )
        if len(normalized_by_metric) < cls.MIN_METRICS_FOR_RANKING:
            return True, (
                f"Only {len(normalized_by_metric)} metric(s) survived validation, below the "
                f"{cls.MIN_METRICS_FOR_RANKING} required for a stable ranking. A score built "
                "on so few indicators would swing on any one of them."
            )

        top, runner_up = scored[0], scored[1]
        margin = (top.overall_score or 0.0) - (runner_up.overall_score or 0.0)
        if margin < cls.MIN_SCORE_MARGIN:
            return True, (
                f"{top.geography.display_name} and {runner_up.geography.display_name} are "
                f"separated by {margin:.2f} points on a 0-100 scale. That margin is smaller "
                "than the uncertainty implied by survey margins of error, so the leader "
                "cannot be reliably distinguished from the runner-up."
            )

        # Normalization rescales the candidate set onto 0-100, which manufactures a wide
        # apparent gap even when the underlying values are nearly identical. This is most
        # acute with two candidates, where min-max always yields 0 and 100. Check the raw
        # values directly before presenting the ordering as meaningful.
        separation = cls._median_relative_separation(package, top, runner_up, normalized_by_metric)
        if separation is not None and separation < cls.MIN_RAW_SEPARATION:
            return True, (
                f"{top.geography.display_name} and {runner_up.geography.display_name} differ "
                f"by a median of {separation:.2%} across the underlying Atlas values. The "
                "normalized scores look far apart only because normalization rescales the "
                "candidate set onto 0-100; the regions are effectively indistinguishable on "
                "this evidence."
            )

        return False, None

    @staticmethod
    def _median_relative_separation(
        package: EvidencePackage,
        top: RankedRegion,
        runner_up: RankedRegion,
        normalized_by_metric: dict[str, dict[str, float]],
    ) -> float | None:
        gaps: list[float] = []
        for metric_id in normalized_by_metric:
            values = {}
            for item in package.for_metric(metric_id):
                if item.is_usable and item.raw_value is not None:
                    values[item.geography.slug] = float(item.raw_value)
            first = values.get(top.geography.slug)
            second = values.get(runner_up.geography.slug)
            if first is None or second is None:
                continue
            scale = max(abs(first), abs(second))
            if scale == 0:
                continue
            gaps.append(abs(first - second) / scale)
        if not gaps:
            return None
        return statistics.median(gaps)

    @staticmethod
    def _hash(
        package: EvidencePackage,
        metrics: dict[str, MetricDefinition],
        category_weights: dict[MetricCategory, float],
    ) -> str:
        """Fingerprint every input to the calculation so a run can be re-verified."""
        payload = {
            "geographies": sorted(geography.slug for geography in package.geographies),
            "category_weights": {str(k): round(v, 6) for k, v in sorted(category_weights.items())},
            "metrics": sorted(
                (
                    {
                        "metric_id": metric.metric_id,
                        "atlas_datapoint": metric.atlas_datapoint,
                        "weight": metric.weight,
                        "direction": str(metric.direction),
                        "normalization": str(metric.normalization),
                    }
                    for metric in metrics.values()
                ),
                key=lambda entry: entry["metric_id"],
            ),
            "observations": sorted(
                [
                    [
                        item.geography.slug,
                        item.atlas_datapoint,
                        item.period,
                        item.source,
                        item.raw_value,
                        str(item.validation_status),
                    ]
                    for item in package.items
                ]
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]


def score_regions(
    package: EvidencePackage,
    metrics: dict[str, MetricDefinition],
    config: ScoringConfig | None = None,
) -> ScoringOutput:
    return ScoringService(config).score(package, metrics)
