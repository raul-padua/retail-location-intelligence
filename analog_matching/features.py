"""Matching-feature registry for analog-store search.

Only public ACS-shaped county features enter the distance vector. Outcome variables
(annual sales, gross margin, performance roll-ups) are explicitly forbidden — attaching
them would leak the label we are trying to approximate.
"""

from __future__ import annotations

from market_discovery.features import FEATURE_BY_ID, FEATURE_REGISTRY, FEATURE_SET_VERSION

MATCHER_VERSION = "analog_v1"

# Subset of the public market registry used for store↔market similarity.
MATCHING_FEATURE_IDS: tuple[str, ...] = tuple(
    feature.feature_id for feature in FEATURE_REGISTRY
)

# Fixed weights (must remain stable for reproducibility).
FEATURE_WEIGHTS: dict[str, float] = {
    "population_total": 0.8,
    "population_density": 1.0,
    "median_household_income": 1.3,
    "pct_bachelor_or_higher": 1.1,
    "median_age": 0.9,
    "pct_age_25_44": 1.0,
    "pct_owner_occupied": 0.7,
    "mean_commute_minutes": 0.8,
    "labor_force_participation": 0.9,
    "pct_renter_occupied": 0.7,
}

FORBIDDEN_OUTCOME_FEATURES: frozenset[str] = frozenset(
    {
        "annual_sales_usd",
        "gross_margin_pct",
        "total_annual_sales_usd",
        "monthly_sales_usd",
        "store_performance",
        "segment_share_pct",
    }
)

# Categorical soft-match penalties (added to Euclidean distance, not z-scored).
FORMAT_MISMATCH_PENALTY = 0.18
CLUSTER_MATCH_BONUS = 0.08

# Weak / insufficient analogy thresholds (on similarity in [0, 1]).
MIN_STRONG_SIMILARITY = 0.72
MIN_MODERATE_SIMILARITY = 0.55
MIN_PEER_COUNT = 3
DEFAULT_TOP_K = 5
MAX_TOP_K = 20


def matching_feature_registry_view() -> list[dict]:
    rows: list[dict] = []
    for feature_id in MATCHING_FEATURE_IDS:
        definition = FEATURE_BY_ID[feature_id]
        rows.append(
            {
                **definition.model_dump(mode="json"),
                "weight": FEATURE_WEIGHTS.get(feature_id, 1.0),
                "used_in_matching": True,
            }
        )
    return rows


def assert_no_outcome_leakage(feature_ids: tuple[str, ...]) -> None:
    leaked = set(feature_ids) & FORBIDDEN_OUTCOME_FEATURES
    if leaked:
        raise ValueError(f"Outcome features must not enter matching vector: {sorted(leaked)}")


assert_no_outcome_leakage(MATCHING_FEATURE_IDS)
