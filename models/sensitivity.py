"""Results of the deterministic sensitivity and strategy-profile analyses.

A single ranking answers "which region wins under these weights". It does not answer the
question an executive actually has, which is "is that a fact about the market or a fact
about my weights". These models carry the second answer, and every number in them comes
from re-running the same scoring service over the same evidence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from models.metrics import MetricCategory


class StrategyProfile(BaseModel):
    """A named set of category weights, offered as a decision lens.

    Explicitly not a claim about which weighting is correct. Each profile encodes a
    different, defensible way of reading the same market, and the value of running them
    all is seeing whether the answer survives the disagreement.
    """

    model_config = {"frozen": True}

    profile_id: str
    display_name: str
    description: str
    when_to_use: str
    category_weights: dict[MetricCategory, float]


class RegionScore(BaseModel):
    model_config = {"frozen": True}

    slug: str
    display_name: str
    rank: int
    overall_score: float | None


class ProfileRanking(BaseModel):
    """One profile's ranking, with its own reproducibility hash."""

    model_config = {"frozen": True}

    profile_id: str
    display_name: str
    reproducibility_hash: str
    regions: list[RegionScore]
    insufficient_evidence: bool = False
    insufficient_reason: str | None = None

    @property
    def winner(self) -> RegionScore | None:
        return self.regions[0] if self.regions else None


class RankDelta(BaseModel):
    """How one region moved between two rankings."""

    model_config = {"frozen": True}

    slug: str
    display_name: str
    baseline_rank: int
    comparison_rank: int
    baseline_score: float | None
    comparison_score: float | None

    @property
    def rank_change(self) -> int:
        """Positive means the region improved, which is a *lower* rank number."""
        return self.baseline_rank - self.comparison_rank

    @property
    def score_change(self) -> float | None:
        if self.baseline_score is None or self.comparison_score is None:
            return None
        return round(self.comparison_score - self.baseline_score, 4)


class ProfileComparison(BaseModel):
    model_config = {"frozen": True}

    baseline: ProfileRanking
    profiles: list[ProfileRanking] = Field(default_factory=list)
    deltas: dict[str, list[RankDelta]] = Field(default_factory=dict)
    stable: bool = True
    stability_note: str = ""

    @property
    def winners(self) -> dict[str, str]:
        result = {}
        if self.baseline.winner:
            result[self.baseline.profile_id] = self.baseline.winner.display_name
        for profile in self.profiles:
            if profile.winner:
                result[profile.profile_id] = profile.winner.display_name
        return result


class MetricInfluence(BaseModel):
    """How much one metric contributed to one region's overall score."""

    model_config = {"frozen": True}

    slug: str
    display_name: str
    metric_id: str
    metric_name: str
    category: MetricCategory
    normalized_value: float
    contribution: float
    """Points of the 0-100 overall score attributable to this metric."""

    share_of_score: float
    """Contribution as a fraction of the region's overall score."""


class FlipPoint(BaseModel):
    """What it would take to reverse the top two regions by moving one category weight."""

    model_config = {"frozen": True}

    category: MetricCategory
    current_weight: float
    flips: bool
    required_weight: float | None = None
    direction: str | None = None
    note: str = ""


class SensitivityReport(BaseModel):
    model_config = {"frozen": True}

    comparison: ProfileComparison
    influences: list[MetricInfluence] = Field(default_factory=list)
    flip_points: list[FlipPoint] = Field(default_factory=list)
    resolution: float = 0.01
    """Weight step size used when searching for a flip point."""

    @property
    def recommendation_is_assumption_sensitive(self) -> bool:
        return not self.comparison.stable

    def influences_for(self, slug: str) -> list[MetricInfluence]:
        return sorted(
            (entry for entry in self.influences if entry.slug == slug),
            key=lambda entry: entry.contribution,
            reverse=True,
        )
