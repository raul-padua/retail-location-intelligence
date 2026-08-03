"""Attach public-market host context to simulated stores (presentation / peer profiling).

Host county and archetype come from the market-discovery artifact. This does not change
generation math; it only labels where a fictional store sits relative to public archetypes
so the demo UI can profile performance in markets like the selected candidate.
"""

from __future__ import annotations

import statistics

from market_discovery.artifact import LoadedArtifact
from market_discovery.service import get_market_discovery_service
from models.provenance import DataClass, data_class_view
from retailer_simulation.models import SimulatedStore, SimulationArtifact


def enrich_stores_with_host_markets(
    stores: list[SimulatedStore],
    *,
    discovery_artifact: LoadedArtifact | None = None,
) -> list[SimulatedStore]:
    # Lazy import avoids a circular dependency with analog_matching.service.
    from analog_matching.matcher import assign_host_county

    artifact = discovery_artifact or get_market_discovery_service().artifact
    enriched: list[SimulatedStore] = []
    for store in stores:
        geoid, name = assign_host_county(store, artifact)
        assignment = artifact.assignment(geoid)
        enriched.append(
            store.model_copy(
                update={
                    "host_geoid": geoid,
                    "host_name": name,
                    "host_cluster_id": assignment.cluster_id if assignment else None,
                }
            )
        )
    return enriched


def similar_market_profile(
    stores: list[SimulatedStore],
    *,
    cluster_id: str | None,
    cluster_label: str | None = None,
    focus_market_name: str | None = None,
) -> dict | None:
    """Aggregate simulated performance for stores hosted in the same archetype."""
    if not cluster_id:
        return None
    peers = [store for store in stores if store.host_cluster_id == cluster_id]
    if not peers:
        return {
            "cluster_id": cluster_id,
            "cluster_label": cluster_label,
            "focus_market_name": focus_market_name,
            "store_count": 0,
            "median_annual_sales_usd": None,
            "iqr_annual_sales_usd": None,
            "median_gross_margin_pct": None,
            "store_ids": [],
            "note": (
                "No simulated stores fall in this market archetype in the current run. "
                "Try a larger store count or a different seed."
            ),
            "data_class": data_class_view(DataClass.SIMULATED_RETAILER_DATA),
        }

    sales = sorted(store.annual_sales_usd for store in peers)
    margins = sorted(store.gross_margin_pct for store in peers)
    q1, q3 = _quartiles(sales)
    return {
        "cluster_id": cluster_id,
        "cluster_label": cluster_label,
        "focus_market_name": focus_market_name,
        "store_count": len(peers),
        "median_annual_sales_usd": statistics.median(sales),
        "iqr_annual_sales_usd": {
            "q1": q1,
            "q3": q3,
        },
        "median_gross_margin_pct": statistics.median(margins),
        "store_ids": [store.store_id for store in peers],
        "note": (
            "Demo profile of fictional NorthStar stores hosted in counties that share the "
            "selected area's public-market archetype — not a forecast for the candidate."
        ),
        "data_class": data_class_view(DataClass.SIMULATED_RETAILER_DATA),
    }


def _quartiles(values: list[float]) -> tuple[float, float]:
    if len(values) == 1:
        return values[0], values[0]
    mid = len(values) // 2
    lower = values[:mid] if len(values) % 2 == 0 else values[:mid]
    upper = values[mid:] if len(values) % 2 == 0 else values[mid + 1 :]
    if not lower:
        lower = values[:1]
    if not upper:
        upper = values[-1:]
    return float(statistics.median(lower)), float(statistics.median(upper))


def enrich_artifact(artifact: SimulationArtifact) -> SimulationArtifact:
    return artifact.model_copy(
        update={"stores": enrich_stores_with_host_markets(artifact.stores)}
    )
