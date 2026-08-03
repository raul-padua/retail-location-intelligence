"""Public market feature registry.

Each feature is an ACS (or ACS-derived) quantity with an explicit source, transform, and
retail rationale. Clustering consumes only these ids; inventing a column name elsewhere
is a schema error, not a silent drop-in.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MissingPolicy(StrEnum):
    MEDIAN_IMPUTE = "median_impute"
    DROP_ROW = "drop_row"


class MarketFeatureDef(BaseModel):
    model_config = {"frozen": True}

    feature_id: str
    display_name: str
    acs_variables: list[str] = Field(
        description="Census ACS variable ids used to construct the feature"
    )
    source_url: str
    period: str
    unit: str
    transform: str
    retail_rationale: str
    missing_policy: MissingPolicy = MissingPolicy.MEDIAN_IMPUTE
    caveats: str
    higher_is: str = Field(
        description="Whether a higher raw value means more of the named concept"
    )


# ACS 5-year 2022 variable definitions (Census Bureau).
# https://api.census.gov/data/2022/acs/acs5/variables.html
FEATURE_REGISTRY: tuple[MarketFeatureDef, ...] = (
    MarketFeatureDef(
        feature_id="population_total",
        display_name="Total population",
        acs_variables=["B01003_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="people",
        transform="log1p",
        retail_rationale="Market size for store-count and format screening.",
        caveats="Administrative county population, not trade-area catchment.",
        higher_is="larger resident base",
    ),
    MarketFeatureDef(
        feature_id="population_density",
        display_name="Population density",
        acs_variables=["B01003_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="people per sq mi",
        transform="log1p",
        retail_rationale="Urban vs dispersed demand patterns and format fit.",
        caveats="Uses county land area from the artifact; water area excluded where known.",
        higher_is="denser settlement",
    ),
    MarketFeatureDef(
        feature_id="median_household_income",
        display_name="Median household income",
        acs_variables=["B19013_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="USD",
        transform="identity",
        retail_rationale="Spending-power proxy for mid/premium apparel.",
        caveats="Household median; does not capture visitor or student spend.",
        higher_is="higher income",
    ),
    MarketFeatureDef(
        feature_id="pct_bachelor_or_higher",
        display_name="Share bachelor's or higher (age 25+)",
        acs_variables=["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E", "B15003_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="percent",
        transform="identity",
        retail_rationale="Education mix often correlates with brand affinity for apparel.",
        caveats="Constructed as (bachelor+master+professional+doctorate) / age-25+ total.",
        higher_is="higher education share",
    ),
    MarketFeatureDef(
        feature_id="median_age",
        display_name="Median age",
        acs_variables=["B01002_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="years",
        transform="identity",
        retail_rationale="Age structure for assortment and marketing tone.",
        caveats="County-wide median; intra-county campus pockets are smoothed away.",
        higher_is="older population",
    ),
    MarketFeatureDef(
        feature_id="pct_age_25_44",
        display_name="Share age 25–44",
        acs_variables=["B01001_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="percent",
        transform="identity",
        retail_rationale="Prime working-age cohort for fashion apparel demand.",
        caveats="Fixture may use a pre-aggregated share when full age table is unavailable.",
        higher_is="larger prime-age share",
    ),
    MarketFeatureDef(
        feature_id="pct_owner_occupied",
        display_name="Owner-occupied housing share",
        acs_variables=["B25003_002E", "B25003_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="percent",
        transform="identity",
        retail_rationale="Tenure mix as a stability / suburbanization signal.",
        caveats="High owner share can mean suburban format, not higher spend.",
        higher_is="more owner-occupied",
    ),
    MarketFeatureDef(
        feature_id="mean_commute_minutes",
        display_name="Mean commute time",
        acs_variables=["B08303_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="minutes",
        transform="identity",
        retail_rationale="Time-budget and destination-retail accessibility proxy.",
        caveats="Workers' mean travel time; not a drive-time trade area.",
        higher_is="longer average commute",
    ),
    MarketFeatureDef(
        feature_id="labor_force_participation",
        display_name="Labor-force participation rate",
        acs_variables=["B23025_002E", "B23025_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="percent",
        transform="identity",
        retail_rationale="Workforce engagement as a daytime-economy signal.",
        caveats="Civilian labor force / population 16+; students and retirees dilute it.",
        higher_is="higher participation",
    ),
    MarketFeatureDef(
        feature_id="pct_renter_occupied",
        display_name="Renter-occupied housing share",
        acs_variables=["B25003_003E", "B25003_001E"],
        source_url="https://www.census.gov/programs-surveys/acs",
        period="ACS 5-year 2022",
        unit="percent",
        transform="identity",
        retail_rationale="Renter share often tracks denser, younger urban cores.",
        caveats="Complement of owner share when both are present; kept for interpretability.",
        higher_is="more renter-occupied",
    ),
)


FEATURE_BY_ID: dict[str, MarketFeatureDef] = {
    feature.feature_id: feature for feature in FEATURE_REGISTRY
}

FEATURE_SET_VERSION = "acs5_2022_apparel_v1"
CLUSTERING_FEATURE_IDS: tuple[str, ...] = tuple(
    feature.feature_id for feature in FEATURE_REGISTRY
)


def feature_registry_view() -> list[dict]:
    return [feature.model_dump(mode="json") for feature in FEATURE_REGISTRY]
