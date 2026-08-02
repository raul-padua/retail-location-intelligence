"""Metric definitions for the retail location-attractiveness model."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from models.geography import GeographyType


class MetricCategory(StrEnum):
    MARKET_POTENTIAL = "market_potential"
    CUSTOMER_FIT = "customer_fit"
    ECONOMIC_ATTRACTIVENESS = "economic_attractiveness"
    ACCESSIBILITY = "accessibility"
    GROWTH_OUTLOOK = "growth_outlook"


CATEGORY_LABELS: dict[MetricCategory, str] = {
    MetricCategory.MARKET_POTENTIAL: "Market Potential",
    MetricCategory.CUSTOMER_FIT: "Customer Fit",
    MetricCategory.ECONOMIC_ATTRACTIVENESS: "Economic Attractiveness",
    MetricCategory.ACCESSIBILITY: "Accessibility",
    MetricCategory.GROWTH_OUTLOOK: "Growth Outlook",
}

CATEGORY_DESCRIPTIONS: dict[MetricCategory, str] = {
    MetricCategory.MARKET_POTENTIAL: "How many potential customers the area holds.",
    MetricCategory.CUSTOMER_FIT: "How closely residents resemble the target shopper.",
    MetricCategory.ECONOMIC_ATTRACTIVENESS: "How much the area can afford to spend.",
    MetricCategory.ACCESSIBILITY: "How easily people move through the area.",
    MetricCategory.GROWTH_OUTLOOK: "Which direction the market is heading.",
}

CATEGORY_WEIGHT_GUIDANCE: dict[MetricCategory, str] = {
    MetricCategory.MARKET_POTENTIAL: (
        "Raise this when sheer footfall volume matters more than who the shoppers are - a "
        "flagship, a high-turnover format, or a first store in a new market. Lower it when "
        "you are targeting a niche and a large general population does not help you."
    ),
    MetricCategory.CUSTOMER_FIT: (
        "Raise this when the banner is aimed at a specific demographic rather than the "
        "general market, such as a youth or campus-oriented format. Lower it for broad "
        "mainstream apparel, where almost any resident base is a plausible customer."
    ),
    MetricCategory.ECONOMIC_ATTRACTIVENESS: (
        "Raise this for higher price points, where the constraint is what households can "
        "afford rather than how many of them there are. Lower it for value formats, where "
        "a less affluent area can still be a strong market."
    ),
    MetricCategory.ACCESSIBILITY: (
        "Raise this where the catchment depends on people driving in rather than walking "
        "past. Note that this is the thinnest category in the registry - at city level it "
        "rests on commute time alone, so a high weight concentrates the score on one metric."
    ),
    MetricCategory.GROWTH_OUTLOOK: (
        "Raise this for a long lease, where the trajectory over the term matters more than "
        "conditions today. Lower it for a short-term or pop-up commitment, where the "
        "current snapshot is what you are actually buying."
    ),
}


class Direction(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class Unit(StrEnum):
    PEOPLE = "people"
    HOUSEHOLDS = "households"
    ESTABLISHMENTS = "establishments"
    JOBS = "jobs"
    USD = "usd"
    PERCENT = "percent"
    YEARS = "years"
    MINUTES = "minutes"
    COUNT = "count"
    INDEX = "index"
    PEOPLE_PER_YEAR = "people_per_year"


# Extensive units scale with the size of the area: a county necessarily reports more people
# than a city inside it. The validator uses this split to block ranking on a magnitude when
# the candidates sit at different geographic levels.
COUNT_UNITS = {
    Unit.PEOPLE,
    Unit.HOUSEHOLDS,
    Unit.ESTABLISHMENTS,
    Unit.JOBS,
    Unit.COUNT,
    Unit.PEOPLE_PER_YEAR,
}

# Intensive units describe an average or a share and stay meaningful across levels.
RATE_UNITS = {Unit.PERCENT, Unit.INDEX}


class Normalization(StrEnum):
    MIN_MAX = "min_max"
    """Scale linearly to 0-100 across the candidate set. Preserves the relative size of
    gaps, which is what a reader expects, but a single extreme region compresses the rest."""

    RANK = "rank"
    """Percentile rank within the candidate set. Discards gap magnitude but is unaffected
    by an outlier, which matters when one candidate is far larger than the others.

    Rank is preferred over z-score clamping here because a z-score is bounded by
    sqrt(n-1) for n candidates, so clamping at two standard deviations never activates
    for the small candidate sets this tool is built for."""


class MetricDefinition(BaseModel):
    """A single verified Atlas datapoint used by the scoring model.

    Every field here is asserted at registry-load time against the verification artifact
    produced by ``scripts/verify_datapoints.py``. A metric that Atlas did not actually
    return cannot enter the registry.
    """

    model_config = {"frozen": True}

    metric_id: str = Field(description="Stable internal id, e.g. 'total_population'")
    display_name: str
    atlas_datapoint: str = Field(description="Verified Atlas datapoint identifier")
    category: MetricCategory
    unit: Unit
    direction: Direction
    weight: float = Field(gt=0.0, description="Relative weight within its category")
    source: str = Field(description="Attribution string returned by Atlas metadata")
    expected_periods: list[str] = Field(
        default_factory=list,
        description="Periods observed during verification, newest first",
    )
    supported_geography_types: list[GeographyType]
    normalization: Normalization = Normalization.MIN_MAX
    retail_rationale: str = Field(description="Why a retailer should care about this metric")
    notes: str | None = None

    atlas_collection: str | None = Field(
        default=None,
        description="Set when the datapoint lives inside an Atlas collection",
    )
    atlas_item_datapoint: str | None = Field(
        default=None, description="Datapoint used to filter collection items, e.g. a NAICS code"
    )
    atlas_item_code: str | None = Field(
        default=None, description="Collection item to select, e.g. NAICS '44' for retail trade"
    )

    @property
    def is_count(self) -> bool:
        return self.unit in COUNT_UNITS

    @property
    def is_rate(self) -> bool:
        return self.unit in RATE_UNITS

    @property
    def is_collection_metric(self) -> bool:
        return self.atlas_collection is not None

    def supports(self, geography_type: GeographyType) -> bool:
        return geography_type in self.supported_geography_types
