"""Query and run API for the NorthStar Apparel fictional retailer simulator."""

from __future__ import annotations

from functools import lru_cache

from market_discovery.geography_bridge import GeographyLevelMismatch
from market_discovery.service import UnknownMarketError, get_market_discovery_service
from models.provenance import DataClass, data_class_view
from retailer_simulation.benchmarks import (
    benchmarks_view,
    get_benchmark_catalog,
)
from retailer_simulation.enrichment import enrich_artifact, similar_market_profile
from retailer_simulation.generator import generate_simulation
from retailer_simulation.models import (
    BRAND_NAME,
    SIMULATOR_VERSION,
    RetailerScenario,
    SimulationArtifact,
)


class RetailerSimulationService:
    def __init__(self, catalog_path: str | None = None) -> None:
        self._catalog_path = catalog_path

    @property
    def catalog(self):
        return get_benchmark_catalog(self._catalog_path)

    def meta(self) -> dict:
        catalog = self.catalog
        return {
            "simulator_version": SIMULATOR_VERSION,
            "brand": BRAND_NAME,
            "benchmark_version": catalog.version,
            "data_class": data_class_view(DataClass.SIMULATED_RETAILER_DATA),
            "provenance_notes": catalog.provenance_notes
            + [
                "NorthStar Apparel is fictional simulated data for demo exploration.",
                "Never presented as real GAP or any retailer store performance.",
            ],
        }

    def benchmarks(self) -> dict:
        return benchmarks_view(self.catalog)

    def default_scenario(self) -> RetailerScenario:
        return RetailerScenario()

    def run(self, scenario: RetailerScenario) -> SimulationArtifact:
        return enrich_artifact(generate_simulation(scenario, self.catalog))

    def run_view(
        self,
        scenario: RetailerScenario,
        *,
        focus_market_id: str | None = None,
    ) -> dict:
        artifact = self.run(scenario)
        return simulation_view(artifact, focus_market_id=focus_market_id)


def simulation_view(
    artifact: SimulationArtifact,
    *,
    focus_market_id: str | None = None,
) -> dict:
    # Ensure host markets exist even for artifacts loaded from older sessions.
    if any(store.host_geoid is None for store in artifact.stores):
        artifact = enrich_artifact(artifact)

    payload = artifact.model_dump(mode="json")
    payload["data_class"] = data_class_view(artifact.data_class)
    payload["scenario"] = {
        **artifact.scenario.model_dump(mode="json"),
        "data_class": data_class_view(artifact.scenario.data_class),
    }
    for store in payload["stores"]:
        store["data_class"] = data_class_view(DataClass.SIMULATED_RETAILER_DATA)
    for entry in payload["monthly"]:
        entry["data_class"] = data_class_view(DataClass.SIMULATED_RETAILER_DATA)
    for segment in payload["segments"]:
        segment["data_class"] = data_class_view(DataClass.SIMULATED_RETAILER_DATA)
    for line in payload["reconciliation"]:
        line["data_class"] = data_class_view(DataClass.SIMULATED_RETAILER_DATA)

    payload["similar_market_profile"] = None
    if focus_market_id:
        payload["similar_market_profile"] = _profile_for_focus(
            artifact.stores,
            focus_market_id,
        )
    return payload


def _profile_for_focus(stores, focus_market_id: str) -> dict | None:
    try:
        discovery = get_market_discovery_service()
        profile = discovery.market_profile(focus_market_id)
    except (GeographyLevelMismatch, UnknownMarketError, KeyError):
        return {
            "cluster_id": None,
            "cluster_label": None,
            "focus_market_name": focus_market_id,
            "store_count": 0,
            "median_annual_sales_usd": None,
            "iqr_annual_sales_usd": None,
            "median_gross_margin_pct": None,
            "store_ids": [],
            "note": (
                "The selected geography cannot be mapped to a public-market archetype, "
                "so a similar-market store profile is unavailable."
            ),
            "data_class": data_class_view(DataClass.SIMULATED_RETAILER_DATA),
        }
    return similar_market_profile(
        stores,
        cluster_id=profile.cluster_id,
        cluster_label=profile.label,
        focus_market_name=profile.name,
    )


@lru_cache(maxsize=1)
def get_retailer_simulation_service(catalog_path: str | None = None) -> RetailerSimulationService:
    return RetailerSimulationService(catalog_path=catalog_path)


def clear_service_cache() -> None:
    get_retailer_simulation_service.cache_clear()


def artifact_from_wire(payload: dict) -> SimulationArtifact:
    """Rebuild a typed artifact from a session/wire projection (strips view badges)."""
    from retailer_simulation.models import SimulatedStore

    def _strip(row: dict) -> dict:
        return {key: value for key, value in row.items() if key != "data_class"}

    return SimulationArtifact.model_validate(
        {
            "brand": payload["brand"],
            "simulator_version": payload["simulator_version"],
            "seed": payload["seed"],
            "scenario": _strip(payload["scenario"]),
            "stores": [
                SimulatedStore.model_validate(_strip(row)).model_dump(mode="json")
                for row in payload["stores"]
            ],
            "monthly": [_strip(row) for row in payload["monthly"]],
            "segments": [_strip(row) for row in payload["segments"]],
            "reconciliation": [_strip(row) for row in payload["reconciliation"]],
            "assumptions": payload.get("assumptions", []),
            "provenance_notes": payload.get("provenance_notes", []),
            "reconciliation_passed": payload.get("reconciliation_passed", False),
        }
    )
