"""Deterministic comparison of two plan versions and their results.

When an analysis is rerun after a revision, the interesting output is not the new ranking
but the difference, and specifically *which input caused it*. A model asked to summarise
two results will produce something plausible; asked which weight change moved a region up
two places, it will produce something plausible and occasionally wrong.

So the diff is computed here, from the two plans and the two results, and the model - if
one is involved at all - is only ever handed the finished comparison to phrase.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from models.analysis import AnalysisResult
from models.metrics import CATEGORY_LABELS, MetricCategory
from models.plan import AnalysisPlanProposal
from models.sensitivity import RankDelta


class WeightChange(BaseModel):
    model_config = {"frozen": True}

    category: MetricCategory
    before: float
    after: float

    @property
    def change(self) -> float:
        return round(self.after - self.before, 6)

    def describe(self) -> str:
        return (
            f"{CATEGORY_LABELS[self.category]} moved from {self.before:.0%} to "
            f"{self.after:.0%}."
        )


class PlanDiff(BaseModel):
    """What changed between two plan versions."""

    model_config = {"frozen": True}

    from_plan_id: str
    from_version: int
    to_plan_id: str
    to_version: int

    weight_changes: list[WeightChange] = Field(default_factory=list)
    metrics_added: list[str] = Field(default_factory=list)
    metrics_removed: list[str] = Field(default_factory=list)
    regions_added: list[str] = Field(default_factory=list)
    regions_removed: list[str] = Field(default_factory=list)
    override_changes: list[str] = Field(default_factory=list)
    assumptions_added: list[str] = Field(default_factory=list)
    assumptions_removed: list[str] = Field(default_factory=list)
    revision_summary: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.weight_changes,
                self.metrics_added,
                self.metrics_removed,
                self.regions_added,
                self.regions_removed,
                self.override_changes,
            )
        )

    def describe(self) -> list[str]:
        lines = [change.describe() for change in self.weight_changes]
        if self.metrics_added:
            lines.append("Metrics added: " + ", ".join(self.metrics_added) + ".")
        if self.metrics_removed:
            lines.append("Metrics removed: " + ", ".join(self.metrics_removed) + ".")
        if self.regions_added:
            lines.append("Regions added: " + ", ".join(self.regions_added) + ".")
        if self.regions_removed:
            lines.append("Regions removed: " + ", ".join(self.regions_removed) + ".")
        lines.extend(self.override_changes)
        return lines


class ResultDiff(BaseModel):
    """What changed in the answer, and which plan change accounts for it."""

    model_config = {"frozen": True}

    plan_diff: PlanDiff
    deltas: list[RankDelta] = Field(default_factory=list)
    previous_hash: str | None = None
    new_hash: str | None = None
    leader_changed: bool = False
    previous_leader: str | None = None
    new_leader: str | None = None
    attribution: list[str] = Field(default_factory=list)
    """Which deterministic input changed, stated without claiming a causal magnitude."""

    @property
    def evidence_changed(self) -> bool:
        """Whether the underlying values moved, as opposed to only the weighting."""
        return bool(
            self.plan_diff.regions_added
            or self.plan_diff.regions_removed
            or self.plan_diff.metrics_added
            or self.plan_diff.metrics_removed
        )


def diff_plans(before: AnalysisPlanProposal, after: AnalysisPlanProposal) -> PlanDiff:
    """Field-by-field difference between two plan versions."""
    weight_changes = []
    for category in MetricCategory:
        old = float(before.category_weights.get(category, 0.0))
        new = float(after.category_weights.get(category, 0.0))
        if abs(new - old) > 1e-9:
            weight_changes.append(
                WeightChange(category=category, before=old, after=new)
            )

    before_metrics = set(before.selected_metric_ids)
    after_metrics = set(after.selected_metric_ids)
    before_regions = {g.display_name for g in before.candidate_geographies}
    after_regions = {g.display_name for g in after.candidate_geographies}

    override_changes: list[str] = []
    for metric_id in sorted(set(before.metric_weight_overrides) | set(after.metric_weight_overrides)):
        old_override = before.metric_weight_overrides.get(metric_id)
        new_override = after.metric_weight_overrides.get(metric_id)
        if old_override == new_override:
            continue
        if old_override is None:
            override_changes.append(
                f"{metric_id} now carries a weight override of {new_override:g}."
            )
        elif new_override is None:
            override_changes.append(
                f"{metric_id} returned to its registry default weight."
            )
        else:
            override_changes.append(
                f"{metric_id} weight override moved from {old_override:g} to "
                f"{new_override:g}."
            )

    before_assumptions = {a.assumption for a in before.assumptions}
    after_assumptions = {a.assumption for a in after.assumptions}

    return PlanDiff(
        from_plan_id=before.plan_id,
        from_version=before.version,
        to_plan_id=after.plan_id,
        to_version=after.version,
        weight_changes=weight_changes,
        metrics_added=sorted(after_metrics - before_metrics),
        metrics_removed=sorted(before_metrics - after_metrics),
        regions_added=sorted(after_regions - before_regions),
        regions_removed=sorted(before_regions - after_regions),
        override_changes=override_changes,
        assumptions_added=sorted(after_assumptions - before_assumptions),
        assumptions_removed=sorted(before_assumptions - after_assumptions),
        revision_summary=after.revision_summary,
    )


def _ranking(result: AnalysisResult) -> dict[str, tuple[int, float | None, str]]:
    if result.recommendation is None:
        return {}
    return {
        region.geography.slug: (
            region.rank,
            region.overall_score,
            region.geography.display_name,
        )
        for region in result.recommendation.ranked_regions
    }


def diff_results(
    before: AnalysisResult,
    after: AnalysisResult,
    plan_diff: PlanDiff | None = None,
) -> ResultDiff:
    """Compare two executed analyses, attributing the change to the inputs that moved."""
    if plan_diff is None:
        if before.proposal is None or after.proposal is None:
            raise ValueError(
                "diff_results needs either an explicit plan diff or two results that "
                "each carry the proposal they executed."
            )
        plan_diff = diff_plans(before.proposal, after.proposal)

    old_ranking = _ranking(before)
    new_ranking = _ranking(after)

    deltas = [
        RankDelta(
            slug=slug,
            display_name=display_name,
            baseline_rank=old_ranking[slug][0],
            comparison_rank=rank,
            baseline_score=old_ranking[slug][1],
            comparison_score=score,
        )
        for slug, (rank, score, display_name) in new_ranking.items()
        if slug in old_ranking
    ]
    deltas.sort(key=lambda delta: delta.comparison_rank)

    previous_leader = next(
        (name for _, (rank, _, name) in old_ranking.items() if rank == 1), None
    )
    new_leader = next(
        (name for _, (rank, _, name) in new_ranking.items() if rank == 1), None
    )

    attribution = _attribute(plan_diff, deltas, before, after)

    return ResultDiff(
        plan_diff=plan_diff,
        deltas=deltas,
        previous_hash=before.reproducibility_hash,
        new_hash=after.reproducibility_hash,
        leader_changed=bool(
            previous_leader and new_leader and previous_leader != new_leader
        ),
        previous_leader=previous_leader,
        new_leader=new_leader,
        attribution=attribution,
    )


def _attribute(
    plan_diff: PlanDiff,
    deltas: list[RankDelta],
    before: AnalysisResult,
    after: AnalysisResult,
) -> list[str]:
    """State which inputs changed. Deliberately stops short of claiming a magnitude.

    Saying "raising Growth Outlook by 15 points moved Winooski up two places" implies a
    causal decomposition that a weighted sum does not support when several inputs moved
    at once. What can be said without qualification is which inputs changed and what the
    output did, and that is what this produces.
    """
    lines: list[str] = []

    if plan_diff.is_empty:
        lines.append(
            "No planned input changed between these two versions, so any difference in "
            "the result comes from the underlying Atlas values having been re-fetched."
        )
        return lines

    lines.extend(plan_diff.describe())

    moved = [delta for delta in deltas if delta.rank_change != 0]
    if not moved:
        lines.append(
            "The ordering did not change. The scores moved, but no region overtook "
            "another, which means the ranking is not sensitive to this change."
        )
    else:
        for delta in moved:
            direction = "up" if delta.rank_change > 0 else "down"
            lines.append(
                f"{delta.display_name} moved {direction} "
                f"{abs(delta.rank_change)} place(s), from rank {delta.baseline_rank} to "
                f"rank {delta.comparison_rank}."
            )

    if before.reproducibility_hash != after.reproducibility_hash:
        lines.append(
            f"The reproducibility hash changed from {before.reproducibility_hash} to "
            f"{after.reproducibility_hash}, which confirms the inputs to the calculation "
            "are genuinely different rather than the same run relabelled."
        )

    if not plan_diff.metrics_added and not plan_diff.metrics_removed and not (
        plan_diff.regions_added or plan_diff.regions_removed
    ):
        lines.append(
            "The evidence is identical in both versions: the same Atlas values, periods, "
            "and sources. Only the weighting differs, so this is a change of emphasis "
            "rather than a change of fact."
        )

    return lines
