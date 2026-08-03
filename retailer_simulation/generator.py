"""Deterministic NorthStar Apparel store and performance generator."""

from __future__ import annotations

import numpy as np

from retailer_simulation.benchmarks import active_benchmarks, benchmark_value
from retailer_simulation.models import (
    BRAND_NAME,
    FORMAT_SALES_MULTIPLIERS,
    FORMAT_SQFT_MULTIPLIERS,
    SIMULATOR_VERSION,
    BenchmarkCatalog,
    MonthlyPerformance,
    RetailerScenario,
    SegmentShare,
    SimulatedStore,
    SimulationArtifact,
)
from retailer_simulation.reconciliation import build_reconciliation

_CITIES: tuple[tuple[str, str, float, float], ...] = (
    ("Portland", "ME", 43.6591, -70.2568),
    ("Burlington", "VT", 44.4759, -73.2121),
    ("Manchester", "NH", 42.9956, -71.4548),
    ("Hartford", "CT", 41.7658, -72.6734),
    ("Providence", "RI", 41.8240, -71.4128),
    ("Albany", "NY", 42.6526, -73.7562),
    ("Syracuse", "NY", 43.0481, -76.1474),
    ("Rochester", "NY", 43.1566, -77.6088),
    ("Buffalo", "NY", 42.8864, -78.8784),
    ("Pittsburgh", "PA", 40.4406, -79.9959),
    ("Philadelphia", "PA", 39.9526, -75.1652),
    ("Baltimore", "MD", 39.2904, -76.6122),
    ("Richmond", "VA", 37.5407, -77.4360),
    ("Raleigh", "NC", 35.7796, -78.6382),
    ("Charlotte", "NC", 35.2271, -80.8431),
    ("Atlanta", "GA", 33.7490, -84.3880),
    ("Jacksonville", "FL", 30.3322, -81.6557),
    ("Orlando", "FL", 28.5383, -81.3792),
    ("Tampa", "FL", 27.9506, -82.4572),
    ("Miami", "FL", 25.7617, -80.1918),
    ("Nashville", "TN", 36.1627, -86.7816),
    ("Memphis", "TN", 35.1495, -90.0490),
    ("Louisville", "KY", 38.2527, -85.7585),
    ("Indianapolis", "IN", 39.7684, -86.1581),
    ("Columbus", "OH", 39.9612, -82.9988),
    ("Cleveland", "OH", 41.4993, -81.6944),
    ("Cincinnati", "OH", 39.1031, -84.5120),
    ("Detroit", "MI", 42.3314, -83.0458),
    ("Milwaukee", "WI", 43.0389, -87.9065),
    ("Minneapolis", "MN", 44.9778, -93.2650),
    ("Des Moines", "IA", 41.5868, -93.6250),
    ("Kansas City", "MO", 39.0997, -94.5786),
    ("St. Louis", "MO", 38.6270, -90.1994),
    ("Omaha", "NE", 41.2565, -95.9345),
    ("Denver", "CO", 39.7392, -104.9903),
    ("Salt Lake City", "UT", 40.7608, -111.8910),
    ("Phoenix", "AZ", 33.4484, -112.0740),
    ("Albuquerque", "NM", 35.0844, -106.6504),
    ("Dallas", "TX", 32.7767, -96.7970),
    ("Houston", "TX", 29.7604, -95.3698),
    ("Austin", "TX", 30.2672, -97.7431),
    ("San Antonio", "TX", 29.4241, -98.4936),
    ("Oklahoma City", "OK", 35.4676, -97.5164),
    ("Seattle", "WA", 47.6062, -122.3321),
    ("Portland", "OR", 45.5152, -122.6784),
    ("Boise", "ID", 43.6150, -116.2023),
    ("Sacramento", "CA", 38.5816, -121.4944),
    ("San Francisco", "CA", 37.7749, -122.4194),
)

_MONTH_LABELS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_SEASONALITY = np.array(
    [0.92, 0.88, 0.95, 1.0, 1.05, 1.08, 1.02, 0.98, 0.90, 0.95, 1.15, 1.12],
    dtype=float,
)
_SEASONALITY /= _SEASONALITY.sum()

_SEGMENT_DEFS: tuple[tuple[str, str], ...] = (
    ("families", "Families"),
    ("young_professionals", "Young professionals"),
    ("value_seekers", "Value seekers"),
    ("teens", "Teens & students"),
)


def _assign_formats(scenario: RetailerScenario, rng: np.random.Generator) -> list[str]:
    formats = list(scenario.format_mix.keys())
    weights = np.array([scenario.format_mix[fmt] for fmt in formats], dtype=float)
    weights /= weights.sum()
    indices = rng.choice(len(formats), size=scenario.store_count, p=weights)
    return [formats[int(index)] for index in indices]


def _pick_cities(scenario: RetailerScenario, rng: np.random.Generator) -> list[tuple[str, str, float, float]]:
    indices = rng.choice(len(_CITIES), size=scenario.store_count, replace=scenario.store_count > len(_CITIES))
    return [_CITIES[int(index)] for index in indices]


def generate_simulation(
    scenario: RetailerScenario,
    catalog: BenchmarkCatalog,
) -> SimulationArtifact:
    """Build a fully deterministic artifact for the given scenario and seed."""
    rng = np.random.default_rng(scenario.seed)
    anchor_sales = benchmark_value(catalog, "avg_annual_store_sales_usd")
    anchor_sqft = benchmark_value(catalog, "avg_store_sq_ft")
    anchor_margin = benchmark_value(catalog, "gross_margin_pct")

    formats = _assign_formats(scenario, rng)
    cities = _pick_cities(scenario, rng)
    noise = rng.lognormal(mean=0.0, sigma=0.12, size=scenario.store_count)

    raw_sales = np.array(
        [
            anchor_sales
            * FORMAT_SALES_MULTIPLIERS.get(fmt, 1.0)
            * float(noise[index])
            for index, fmt in enumerate(formats)
        ],
        dtype=float,
    )
    scale = scenario.sales_target_usd / float(raw_sales.sum())
    scaled_sales = raw_sales * scale

    margin_spread = scenario.margin_max_pct - scenario.margin_min_pct
    margin_noise = rng.uniform(0.0, 1.0, size=scenario.store_count)
    margins = scenario.margin_min_pct + margin_noise * margin_spread
    # Pull toward public anchor without leaving the user range.
    margins = np.clip(0.6 * margins + 0.4 * anchor_margin, scenario.margin_min_pct, scenario.margin_max_pct)

    stores: list[SimulatedStore] = []
    for index in range(scenario.store_count):
        city, state, lat, lon = cities[index]
        fmt = formats[index]
        jitter_lat = float(lat + rng.uniform(-0.08, 0.08))
        jitter_lon = float(lon + rng.uniform(-0.08, 0.08))
        sq_ft = anchor_sqft * FORMAT_SQFT_MULTIPLIERS.get(fmt, 1.0) * float(rng.uniform(0.92, 1.08))
        stores.append(
            SimulatedStore(
                store_id=f"NS-{index + 1:03d}",
                name=f"NorthStar {city} {fmt.title()}",
                format=fmt,
                city=city,
                state=state,
                lat=jitter_lat,
                lon=jitter_lon,
                sq_ft=round(sq_ft, 1),
                annual_sales_usd=round(float(scaled_sales[index]), 2),
                gross_margin_pct=round(float(margins[index]), 2),
            )
        )

    total_annual = float(sum(store.annual_sales_usd for store in stores))
    monthly: list[MonthlyPerformance] = []
    for month_index, label in enumerate(_MONTH_LABELS, start=1):
        month_sales = total_annual * float(_SEASONALITY[month_index - 1])
        monthly.append(
            MonthlyPerformance(
                month=month_index,
                label=label,
                total_sales_usd=round(month_sales, 2),
                store_count=scenario.store_count,
            )
        )

    segment_raw = rng.dirichlet(np.array([2.4, 1.8, 2.0, 1.2], dtype=float))
    segments = [
        SegmentShare(
            segment_id=segment_id,
            label=label,
            share_pct=round(float(share) * 100.0, 2),
        )
        for (segment_id, label), share in zip(_SEGMENT_DEFS, segment_raw, strict=True)
    ]

    reconciliation = build_reconciliation(
        scenario=scenario,
        stores=stores,
        segments=segments,
        monthly=monthly,
        catalog=catalog,
    )
    assumptions = [
        f"Fictional brand {BRAND_NAME}; not observed retailer performance.",
        f"Scenario store_count={scenario.store_count} and sales_target_usd={scenario.sales_target_usd:,.0f} are explicit user assumptions.",
        "Public benchmarks anchor per-store sales and margin; disabled benchmarks are ignored.",
        f"Format mix: {', '.join(f'{k}={v:.0%}' for k, v in scenario.format_mix.items())}.",
    ]
    provenance_notes = list(catalog.provenance_notes) + [
        f"Generated by {SIMULATOR_VERSION} with seed {scenario.seed}.",
        f"Active benchmarks: {len(active_benchmarks(catalog))}; disabled entries excluded from generation.",
    ]

    return SimulationArtifact(
        brand=BRAND_NAME,
        simulator_version=SIMULATOR_VERSION,
        seed=scenario.seed,
        scenario=scenario,
        stores=stores,
        monthly=monthly,
        segments=segments,
        reconciliation=reconciliation,
        assumptions=assumptions,
        provenance_notes=provenance_notes,
        reconciliation_passed=all(line.passed for line in reconciliation),
    )
