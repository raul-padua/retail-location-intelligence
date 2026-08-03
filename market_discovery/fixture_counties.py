"""Deterministic ACS-shaped county fixture for offline demos and tests.

Values are synthetic but anchored to publicly known approximate magnitudes for the
Vermont demo counties and a national peer set. The build script can replace this with a
live ACS pull when network access and a Census API key (optional) are available.

Every feature id matches ``market_discovery.features.FEATURE_REGISTRY``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from market_discovery.models import CountyRecord
from market_discovery.pipeline import DEFAULT_MIN_POPULATION


@dataclass(frozen=True)
class _SeedCounty:
    geoid: str
    name: str
    population: float
    land_area_sq_mi: float
    lat: float
    lon: float
    median_household_income: float
    pct_bachelor_or_higher: float
    median_age: float
    pct_age_25_44: float
    pct_owner_occupied: float
    mean_commute_minutes: float
    labor_force_participation: float


# Mix of VT demo counties + peers across income/density/education archetypes.
_SEEDS: tuple[_SeedCounty, ...] = (
    _SeedCounty("50007", "Chittenden County, Vermont", 168300, 536.0, 44.46, -73.08, 89400, 52.1, 36.8, 28.4, 62.0, 21.5, 69.2),
    _SeedCounty("50011", "Franklin County, Vermont", 50300, 634.0, 44.86, -72.91, 72100, 28.4, 41.2, 24.1, 78.5, 26.8, 67.0),
    _SeedCounty("50013", "Grand Isle County, Vermont", 7400, 81.8, 44.72, -73.30, 81200, 39.5, 48.1, 18.9, 84.2, 32.4, 61.5),
    _SeedCounty("50001", "Addison County, Vermont", 37300, 766.0, 44.03, -73.12, 74500, 38.0, 43.5, 22.0, 76.0, 24.0, 65.0),
    _SeedCounty("50021", "Rutland County, Vermont", 60500, 929.0, 43.58, -73.04, 61200, 30.2, 46.0, 21.5, 74.0, 23.5, 62.0),
    _SeedCounty("50023", "Washington County, Vermont", 58400, 687.0, 44.27, -72.62, 70200, 41.0, 43.0, 23.8, 72.0, 22.8, 66.0),
    _SeedCounty("33011", "Hillsborough County, New Hampshire", 427000, 876.0, 42.92, -71.57, 91200, 40.5, 40.8, 26.0, 68.0, 28.5, 70.0),
    _SeedCounty("33015", "Rockingham County, New Hampshire", 318000, 695.0, 42.99, -71.08, 105400, 44.0, 44.2, 24.5, 78.0, 30.2, 69.5),
    _SeedCounty("25017", "Middlesex County, Massachusetts", 1617000, 818.0, 42.49, -71.39, 121700, 58.0, 39.5, 28.0, 62.5, 31.0, 70.5),
    _SeedCounty("25025", "Suffolk County, Massachusetts", 771000, 58.2, 42.33, -71.07, 80300, 49.5, 33.8, 36.0, 34.0, 30.5, 68.0),
    _SeedCounty("09001", "Fairfield County, Connecticut", 957000, 625.0, 41.23, -73.37, 105200, 49.0, 41.0, 25.5, 68.5, 32.0, 67.5),
    _SeedCounty("09003", "Hartford County, Connecticut", 896000, 735.0, 41.81, -72.73, 80300, 38.5, 40.5, 26.2, 64.0, 25.0, 66.5),
    _SeedCounty("36061", "New York County, New York", 1596000, 22.7, 40.78, -73.97, 93600, 62.0, 37.5, 34.5, 24.0, 35.0, 67.0),
    _SeedCounty("36047", "Kings County, New York", 2672000, 69.4, 40.65, -73.95, 74600, 40.5, 35.8, 31.0, 30.0, 41.0, 64.5),
    _SeedCounty("36059", "Nassau County, New York", 1387000, 285.0, 40.73, -73.59, 136000, 48.0, 42.0, 23.5, 81.0, 37.0, 66.0),
    _SeedCounty("34003", "Bergen County, New Jersey", 953000, 233.0, 40.96, -74.07, 112400, 51.0, 42.5, 24.8, 66.0, 33.0, 67.0),
    _SeedCounty("06037", "Los Angeles County, California", 9821000, 4058.0, 34.05, -118.24, 77400, 35.0, 37.0, 30.0, 46.0, 31.5, 64.0),
    _SeedCounty("06075", "San Francisco County, California", 851000, 46.9, 37.77, -122.42, 136700, 60.0, 38.5, 35.0, 38.0, 33.0, 70.0),
    _SeedCounty("06085", "Santa Clara County, California", 1888000, 1291.0, 37.36, -121.97, 153000, 56.0, 37.8, 31.5, 56.0, 28.0, 68.5),
    _SeedCounty("17031", "Cook County, Illinois", 5163000, 945.0, 41.84, -87.68, 74600, 41.0, 37.5, 29.5, 58.0, 33.5, 65.5),
    _SeedCounty("48201", "Harris County, Texas", 4781000, 1704.0, 29.76, -95.37, 70800, 33.5, 34.5, 31.0, 55.0, 29.5, 66.0),
    _SeedCounty("48113", "Dallas County, Texas", 2606000, 873.0, 32.78, -96.80, 70500, 34.0, 34.0, 32.0, 50.0, 27.5, 67.5),
    _SeedCounty("04013", "Maricopa County, Arizona", 4492000, 9200.0, 33.45, -112.07, 77300, 34.5, 37.0, 28.0, 64.0, 26.5, 64.0),
    _SeedCounty("12086", "Miami-Dade County, Florida", 2686000, 1898.0, 25.76, -80.19, 61300, 32.0, 41.0, 27.0, 53.0, 31.0, 63.0),
    _SeedCounty("12011", "Broward County, Florida", 1944000, 1205.0, 26.15, -80.20, 66100, 34.0, 41.5, 26.5, 63.0, 28.0, 64.5),
    _SeedCounty("13121", "Fulton County, Georgia", 1084000, 527.0, 33.79, -84.47, 88300, 54.0, 35.5, 33.0, 52.0, 28.5, 68.0),
    _SeedCounty("13089", "DeKalb County, Georgia", 762000, 268.0, 33.77, -84.30, 72500, 45.0, 36.0, 31.0, 55.0, 32.0, 67.0),
    _SeedCounty("53033", "King County, Washington", 2255000, 2115.0, 47.55, -122.15, 116700, 55.0, 37.0, 32.5, 56.0, 29.0, 70.0),
    _SeedCounty("41051", "Multnomah County, Oregon", 803000, 431.0, 45.52, -122.68, 83600, 50.0, 37.5, 33.0, 53.0, 26.0, 69.0),
    _SeedCounty("08031", "Denver County, Colorado", 711000, 153.0, 39.74, -104.99, 88500, 53.0, 34.5, 36.0, 49.0, 25.5, 72.0),
    _SeedCounty("27053", "Hennepin County, Minnesota", 1266000, 554.0, 44.96, -93.27, 91400, 52.0, 37.0, 30.5, 63.0, 24.5, 71.0),
    _SeedCounty("42101", "Philadelphia County, Pennsylvania", 1576000, 134.0, 39.95, -75.16, 57600, 33.0, 34.8, 31.5, 52.0, 33.0, 61.0),
    _SeedCounty("42003", "Allegheny County, Pennsylvania", 1233000, 730.0, 40.44, -80.00, 72500, 43.0, 41.0, 26.0, 65.0, 26.5, 63.5),
    _SeedCounty("24031", "Montgomery County, Maryland", 1057000, 491.0, 39.14, -77.20, 125300, 60.0, 40.0, 27.0, 67.0, 34.0, 69.0),
    _SeedCounty("51059", "Fairfax County, Virginia", 1141000, 391.0, 38.85, -77.28, 145000, 64.0, 38.5, 28.5, 70.0, 32.5, 71.5),
    _SeedCounty("37183", "Wake County, North Carolina", 1152000, 835.0, 35.79, -78.65, 96900, 55.0, 36.5, 31.0, 64.0, 26.0, 70.0),
    _SeedCounty("37119", "Mecklenburg County, North Carolina", 1129000, 524.0, 35.23, -80.84, 79500, 48.0, 35.5, 33.5, 57.0, 26.5, 70.5),
    _SeedCounty("39035", "Cuyahoga County, Ohio", 1242000, 457.0, 41.48, -81.67, 57400, 35.0, 41.5, 25.0, 59.0, 25.0, 62.0),
    _SeedCounty("39049", "Franklin County, Ohio", 1323000, 532.0, 39.97, -83.01, 70800, 42.0, 34.5, 32.0, 52.0, 23.5, 68.0),
    _SeedCounty("26163", "Wayne County, Michigan", 1759000, 612.0, 42.28, -83.26, 52400, 26.0, 38.0, 26.5, 64.0, 26.0, 58.0),
    _SeedCounty("26125", "Oakland County, Michigan", 1270000, 868.0, 42.66, -83.38, 92300, 49.0, 41.5, 25.5, 74.0, 27.0, 66.0),
)


def build_fixture_counties(
    *,
    min_population: int = DEFAULT_MIN_POPULATION,
) -> list[CountyRecord]:
    counties: list[CountyRecord] = []
    for seed in sorted(_SEEDS, key=lambda item: item.geoid):
        density = seed.population / max(seed.land_area_sq_mi, 0.1)
        pct_renter = max(0.0, min(100.0, 100.0 - seed.pct_owner_occupied))
        # Tiny deterministic jitter so near-duplicate profiles still separate slightly,
        # without depending on row order (keyed by geoid digits).
        jitter = (int(seed.geoid) % 97) / 970.0
        features = {
            "population_total": seed.population,
            "population_density": density,
            "median_household_income": seed.median_household_income + jitter * 100,
            "pct_bachelor_or_higher": seed.pct_bachelor_or_higher,
            "median_age": seed.median_age,
            "pct_age_25_44": seed.pct_age_25_44,
            "pct_owner_occupied": seed.pct_owner_occupied,
            "mean_commute_minutes": seed.mean_commute_minutes,
            "labor_force_participation": seed.labor_force_participation,
            "pct_renter_occupied": pct_renter,
        }
        counties.append(
            CountyRecord(
                geoid=seed.geoid,
                name=seed.name,
                state_fips=seed.geoid[:2],
                county_fips=seed.geoid[2:],
                population=seed.population,
                land_area_sq_mi=seed.land_area_sq_mi,
                lat=seed.lat,
                lon=seed.lon,
                features=features,
                in_clustering_universe=seed.population >= min_population,
            )
        )
    return counties


def tiny_fixture_counties(n: int = 24) -> list[CountyRecord]:
    """Compact set for unit tests (all forced into the clustering universe)."""
    base = build_fixture_counties(min_population=0)
    selected = base[:n]
    # Ensure populations clear the default floor for fit tests that use min_population=0.
    return [
        county.model_copy(
            update={
                "population": max(county.population, 60_000),
                "in_clustering_universe": True,
                "features": {
                    **county.features,
                    "population_total": max(county.population, 60_000),
                    "population_density": max(county.population, 60_000)
                    / max(county.land_area_sq_mi, 0.1),
                },
            }
        )
        for county in selected
    ]


def assert_finite_features(counties: list[CountyRecord]) -> None:
    for county in counties:
        for feature_id, value in county.features.items():
            if value is None:
                continue
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                raise ValueError(f"Non-finite {feature_id} for {county.geoid}")
