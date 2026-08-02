"""The approved metric registry.

Every entry below names an Atlas datapoint that was observed returning a value during
verification (``scripts/verify_datapoints.py``). ``MetricRegistry.load`` re-checks each one
against ``data/atlas_verified_datapoints.json`` at import time and refuses to build a
registry containing a datapoint that Atlas never answered. That check is the structural
reason the system cannot present a fabricated identifier: a hallucinated id has no
verification record, so it cannot become a metric, and a metric is the only thing the
orchestrator is allowed to request.

Note on units: Atlas returns ACS percentages as proportions (0.9517 for 95.17%), not as
the 0-100 form the documentation describes. Metrics below record the proportion form and
the UI multiplies for display; no conversion happens before scoring, so normalization
operates on the values Atlas actually returned.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from models.geography import GeographyType
from models.metrics import Direction, MetricCategory, MetricDefinition, Normalization, Unit

VERIFIED_PATH = Path(__file__).resolve().parents[1] / "data" / "atlas_verified_datapoints.json"

ACS = "US Census, ACS"

_ALL_LEVELS = [
    GeographyType.CBSA,
    GeographyType.COUNTY,
    GeographyType.CITY,
]
_COUNTY_AND_UP = [GeographyType.CBSA, GeographyType.COUNTY]


class UnverifiedMetricError(RuntimeError):
    """Raised when a registry entry names a datapoint absent from the verification record."""


_DEFINITIONS: tuple[MetricDefinition, ...] = (
    # ---------------------------------------------------------------- Market potential
    MetricDefinition(
        metric_id="total_population",
        display_name="Total Population",
        atlas_datapoint="dem.acs.pop.total.val",
        category=MetricCategory.MARKET_POTENTIAL,
        unit=Unit.PEOPLE,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.40,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        normalization=Normalization.MIN_MAX,
        retail_rationale=(
            "The size of the resident population bounds the addressable customer base for a "
            "physical store. It is the coarsest but most reliable proxy for trade-area demand."
        ),
    ),
    MetricDefinition(
        metric_id="total_households",
        display_name="Total Households",
        atlas_datapoint="dem.acs.hhd.total.val",
        category=MetricCategory.MARKET_POTENTIAL,
        unit=Unit.HOUSEHOLDS,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.35,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "Apparel purchasing is substantially a household decision, particularly for "
            "children's and family lines, so household count often tracks demand better than "
            "headcount alone."
        ),
    ),
    MetricDefinition(
        metric_id="civilian_labor_force",
        display_name="Civilian Labor Force",
        atlas_datapoint="wkf.acs.emp.16pl.labor.civ.total.val",
        category=MetricCategory.MARKET_POTENTIAL,
        unit=Unit.PEOPLE,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.25,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "The working population is a proxy for daytime presence and for workwear and "
            "commuter-driven apparel demand, which resident counts alone understate."
        ),
    ),
    # ------------------------------------------------------------------- Customer fit
    MetricDefinition(
        metric_id="median_age",
        display_name="Median Age",
        atlas_datapoint="dem.acs.mdage.total.val",
        category=MetricCategory.CUSTOMER_FIT,
        unit=Unit.YEARS,
        direction=Direction.LOWER_IS_BETTER,
        weight=0.30,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "A mainstream apparel banner skews toward younger adult and family shoppers, so a "
            "lower median age is treated as a better fit for this retailer profile."
        ),
        notes=(
            "Direction is a profile assumption, not a property of the data. A retailer "
            "targeting older shoppers should invert it."
        ),
    ),
    MetricDefinition(
        metric_id="bachelors_or_higher_share",
        display_name="Bachelor's Degree or Higher (25+)",
        atlas_datapoint="edu.acs.att.25pl.bachpl.pct",
        category=MetricCategory.CUSTOMER_FIT,
        unit=Unit.PERCENT,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.35,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "Educational attainment correlates with discretionary spending capacity and with "
            "brand-oriented apparel purchasing, independent of headline income."
        ),
    ),
    MetricDefinition(
        metric_id="undergrad_enrollment_share",
        display_name="College / Undergraduate Enrollment Share (3+)",
        atlas_datapoint="edu.acs.enr.3pl.ugrad.pct",
        category=MetricCategory.CUSTOMER_FIT,
        unit=Unit.PERCENT,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.35,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "A large student population signals a concentrated, footfall-heavy, "
            "fashion-responsive segment near campus retail corridors."
        ),
    ),
    # --------------------------------------------------------- Economic attractiveness
    MetricDefinition(
        metric_id="median_household_income",
        display_name="Median Household Income",
        atlas_datapoint="dem.acs.hhd.mdinc.val",
        category=MetricCategory.ECONOMIC_ATTRACTIVENESS,
        unit=Unit.USD,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.40,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "The most direct available proxy for purchasing power in the trade area. Median "
            "is preferred to mean because it is less distorted by a small number of very "
            "high earners."
        ),
    ),
    MetricDefinition(
        metric_id="per_capita_income",
        display_name="Per Capita Income",
        atlas_datapoint="dem.acs.hhd.pcinc.val",
        category=MetricCategory.ECONOMIC_ATTRACTIVENESS,
        unit=Unit.USD,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.25,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "Complements household income by adjusting for household size, which matters "
            "where student or single-person households are concentrated."
        ),
    ),
    MetricDefinition(
        metric_id="employment_rate",
        display_name="Employed Share of Civilian Labor Force",
        atlas_datapoint="wkf.acs.emp.16pl.labor.civ.emp.pct",
        category=MetricCategory.ECONOMIC_ATTRACTIVENESS,
        unit=Unit.PERCENT,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.35,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "Employment stability underpins sustained discretionary spend. Apparel is among "
            "the first categories cut when local employment weakens."
        ),
    ),
    # -------------------------------------------------------------------- Accessibility
    MetricDefinition(
        metric_id="mean_commute_time",
        display_name="Mean Commute Travel Time",
        atlas_datapoint="trn.acs.cmt.mean.val",
        category=MetricCategory.ACCESSIBILITY,
        unit=Unit.MINUTES,
        direction=Direction.LOWER_IS_BETTER,
        weight=1.0,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "Shorter commutes indicate a more compact, accessible catchment where shoppers "
            "can reach a store without a long trip. Reported in minutes."
        ),
        notes=(
            "This is the only accessibility indicator the demo token exposes at every "
            "geographic level; it is a weak proxy for true trade-area accessibility."
        ),
    ),
    # ------------------------------------------------------------------- Growth outlook
    MetricDefinition(
        metric_id="population_growth_rate",
        display_name="Population Average Yearly Change",
        atlas_datapoint="dem.acs.pop.total.aycp",
        category=MetricCategory.GROWTH_OUTLOOK,
        unit=Unit.PERCENT,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.40,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "A store is a multi-year commitment, so the direction of the trade area matters "
            "as much as its current size."
        ),
    ),
    MetricDefinition(
        metric_id="household_growth_rate",
        display_name="Household Average Yearly Change",
        atlas_datapoint="dem.acs.hhd.total.aycp",
        category=MetricCategory.GROWTH_OUTLOOK,
        unit=Unit.PERCENT,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.30,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "Household formation drives new demand for apparel and home-adjacent categories "
            "more directly than raw population change."
        ),
    ),
    MetricDefinition(
        metric_id="income_growth_rate",
        display_name="Household Median Income Average Yearly Change",
        atlas_datapoint="dem.acs.hhd.mdinc.aycp",
        category=MetricCategory.GROWTH_OUTLOOK,
        unit=Unit.PERCENT,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.30,
        source=ACS,
        expected_periods=["2024"],
        supported_geography_types=_ALL_LEVELS,
        retail_rationale=(
            "Rising local incomes expand discretionary budgets. Nominal, so it is not "
            "inflation-adjusted and should not be read as real purchasing-power growth."
        ),
        notes="Nominal growth. Not adjusted for inflation.",
    ),
    # --------------------- Commercial activity (published at county level and above only)
    MetricDefinition(
        metric_id="retail_establishments",
        display_name="Retail Trade Establishments (NAICS 44)",
        atlas_datapoint="ind.cbp.naics.est.val",
        atlas_collection="ind.cbp.naics",
        atlas_item_datapoint="ind.cbp.naics.code",
        atlas_item_code="44",
        category=MetricCategory.MARKET_POTENTIAL,
        unit=Unit.ESTABLISHMENTS,
        direction=Direction.HIGHER_IS_BETTER,
        weight=0.30,
        source="US Census, County Business Patterns",
        expected_periods=["2023"],
        supported_geography_types=_COUNTY_AND_UP,
        retail_rationale=(
            "The density of existing retail establishments proxies for established shopping "
            "activity and co-tenancy: apparel performs better beside other retail, not in "
            "isolation."
        ),
        notes=(
            "County Business Patterns is not published below county level. Requesting it for "
            "a city causes Atlas to answer with the parent county, which the validation layer "
            "detects and excludes."
        ),
    ),
    MetricDefinition(
        metric_id="food_service_establishments",
        display_name="Food Service & Drinking Establishments (NAICS 722)",
        atlas_datapoint="ind.cbp.naics.est.val",
        atlas_collection="ind.cbp.naics",
        atlas_item_datapoint="ind.cbp.naics.code",
        atlas_item_code="722",
        category=MetricCategory.ACCESSIBILITY,
        unit=Unit.ESTABLISHMENTS,
        direction=Direction.HIGHER_IS_BETTER,
        weight=1.0,
        source="US Census, County Business Patterns",
        expected_periods=["2023"],
        supported_geography_types=_COUNTY_AND_UP,
        retail_rationale=(
            "Restaurants and bars are a widely used proxy for destination footfall and "
            "dwell time, which apparel retail depends on."
        ),
        notes="County level and above only, for the same reason as retail establishments.",
    ),
)


class MetricRegistry:
    """Verified metrics, indexed for lookup by the orchestration layer."""

    def __init__(self, definitions: Iterable[MetricDefinition]) -> None:
        self._by_id: dict[str, MetricDefinition] = {
            definition.metric_id: definition for definition in definitions
        }

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, metric_id: object) -> bool:
        return metric_id in self._by_id

    def all(self) -> list[MetricDefinition]:
        return sorted(self._by_id.values(), key=lambda m: (m.category, m.metric_id))

    def get(self, metric_id: str) -> MetricDefinition | None:
        return self._by_id.get(metric_id)

    def require(self, metric_id: str) -> MetricDefinition:
        metric = self._by_id.get(metric_id)
        if metric is None:
            raise KeyError(
                f"{metric_id!r} is not an approved metric. Approved metrics: "
                f"{sorted(self._by_id)}"
            )
        return metric

    def by_category(self, category: MetricCategory) -> list[MetricDefinition]:
        return [metric for metric in self.all() if metric.category == category]

    def supported_for(self, geography_types: Iterable[GeographyType]) -> list[MetricDefinition]:
        """Metrics publishable at every one of the requested geographic levels."""
        types = list(geography_types)
        return [
            metric for metric in self.all() if all(metric.supports(t) for t in types)
        ]

    def unsupported_for(
        self, geography_types: Iterable[GeographyType]
    ) -> list[tuple[MetricDefinition, str]]:
        types = list(geography_types)
        unsupported: list[tuple[MetricDefinition, str]] = []
        for metric in self.all():
            missing = [t for t in types if not metric.supports(t)]
            if missing:
                unsupported.append(
                    (
                        metric,
                        f"{metric.source} does not publish this datapoint at the "
                        + ", ".join(sorted({str(t) for t in missing}))
                        + " level.",
                    )
                )
        return unsupported

    @staticmethod
    def load_verification_record() -> dict[str, dict]:
        if not VERIFIED_PATH.exists():
            raise UnverifiedMetricError(
                f"Verification record {VERIFIED_PATH} is missing. Run "
                "`uv run python scripts/crawl_atlas_catalog.py` then "
                "`uv run python scripts/verify_datapoints.py` to regenerate it."
            )
        return json.loads(VERIFIED_PATH.read_text(encoding="utf-8"))

    @classmethod
    def load(cls, *, enforce_verification: bool = True) -> MetricRegistry:
        if enforce_verification:
            verified = cls.load_verification_record()
            unverified = [
                definition.atlas_datapoint
                for definition in _DEFINITIONS
                if definition.atlas_datapoint not in verified
            ]
            if unverified:
                raise UnverifiedMetricError(
                    "These registry datapoints have no verification record and cannot be "
                    f"used: {sorted(set(unverified))}. Re-run scripts/verify_datapoints.py."
                )
        return cls(_DEFINITIONS)


@lru_cache(maxsize=1)
def get_registry() -> MetricRegistry:
    return MetricRegistry.load()
