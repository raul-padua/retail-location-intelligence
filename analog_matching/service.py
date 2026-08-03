"""Query and run API for analog-store matching."""

from __future__ import annotations

from functools import lru_cache

from analog_matching.features import (
    DEFAULT_TOP_K,
    FEATURE_SET_VERSION,
    MATCHER_VERSION,
    MAX_TOP_K,
    MIN_MODERATE_SIMILARITY,
    MIN_PEER_COUNT,
    MIN_STRONG_SIMILARITY,
    matching_feature_registry_view,
)
from analog_matching.matcher import search_analogs
from analog_matching.models import AnalogSearchResult
from market_discovery.artifact import DEFAULT_ARTIFACT_DIR, LoadedArtifact, load_artifact
from market_discovery.service import MarketDiscoveryService, UnknownMarketError
from models.provenance import DataClass, data_class_view
from retailer_simulation.models import RetailerScenario, SimulationArtifact
from retailer_simulation.service import RetailerSimulationService, get_retailer_simulation_service


class AnalogMatchingService:
    def __init__(
        self,
        discovery: MarketDiscoveryService,
        simulation: RetailerSimulationService,
    ) -> None:
        self._discovery = discovery
        self._simulation = simulation

    @property
    def artifact(self) -> LoadedArtifact:
        return self._discovery.artifact

    def meta(self) -> dict:
        return {
            "matcher_version": MATCHER_VERSION,
            "feature_set_version": FEATURE_SET_VERSION,
            "matching_features": matching_feature_registry_view(),
            "thresholds": {
                "min_strong_similarity": MIN_STRONG_SIMILARITY,
                "min_moderate_similarity": MIN_MODERATE_SIMILARITY,
                "min_peer_count": MIN_PEER_COUNT,
                "default_top_k": DEFAULT_TOP_K,
                "max_top_k": MAX_TOP_K,
            },
            "data_class": data_class_view(DataClass.PUBLIC_MARKET_DATA),
            "provenance_notes": [
                "Candidate markets use public ACS county features (PUBLIC_MARKET_DATA).",
                "Store↔county assignment is nearest lat/lon among artifact counties.",
                "Simulated sales and margins attach only after ranking for display.",
                "NorthStar Apparel is fictional — never real GAP or retailer performance.",
            ],
        }

    def resolve_candidate(self, market_id: str) -> tuple[str, str]:
        geoid = self._discovery.resolve_geoid(market_id)
        county = self.artifact.county(geoid)
        if county is None:
            raise UnknownMarketError(market_id)
        return geoid, county.name

    def search(
        self,
        *,
        market_id: str,
        simulation: SimulationArtifact,
        top_k: int = DEFAULT_TOP_K,
        preferred_format: str | None = None,
    ) -> AnalogSearchResult:
        geoid, name = self.resolve_candidate(market_id)
        bounded_k = max(1, min(top_k, MAX_TOP_K))
        return search_analogs(
            artifact=self.artifact,
            candidate_geoid=geoid,
            candidate_name=name,
            candidate_market_id=market_id,
            simulation=simulation,
            top_k=bounded_k,
            preferred_format=preferred_format,
            matcher_version=MATCHER_VERSION,
            feature_set_version=FEATURE_SET_VERSION,
        )

    def search_with_scenario(
        self,
        *,
        market_id: str,
        scenario: RetailerScenario | None = None,
        top_k: int = DEFAULT_TOP_K,
        preferred_format: str | None = None,
    ) -> AnalogSearchResult:
        chosen = scenario or self._simulation.default_scenario()
        artifact = self._simulation.run(chosen)
        return self.search(
            market_id=market_id,
            simulation=artifact,
            top_k=top_k,
            preferred_format=preferred_format,
        )


def search_view(result: AnalogSearchResult) -> dict:
    payload = result.model_dump(mode="json")
    payload["data_class"] = data_class_view(result.data_class)
    if result.aggregate_range is not None:
        payload["aggregate_range"] = {
            **result.aggregate_range.model_dump(mode="json"),
            "data_class": data_class_view(result.aggregate_range.data_class),
        }
    matches: list[dict] = []
    for match in result.matches:
        row = match.model_dump(mode="json")
        row["data_class"] = data_class_view(match.data_class)
        if match.performance_summary is not None:
            row["performance_summary"] = {
                **match.performance_summary.model_dump(mode="json"),
                "data_class": data_class_view(match.performance_summary.data_class),
            }
        matches.append(row)
    payload["matches"] = matches
    payload["data_class_notes"] = {
        "candidate_profile": data_class_view(DataClass.PUBLIC_MARKET_DATA),
        "match_features": data_class_view(DataClass.PUBLIC_MARKET_DATA),
        "performance_summary": data_class_view(DataClass.SIMULATED_RETAILER_DATA),
    }
    return payload


@lru_cache(maxsize=1)
def get_analog_matching_service(
    artifact_dir: str | None = None,
    catalog_path: str | None = None,
) -> AnalogMatchingService:
    from market_discovery.service import get_market_discovery_service

    discovery = get_market_discovery_service(artifact_dir)
    simulation = get_retailer_simulation_service(catalog_path)
    return AnalogMatchingService(discovery, simulation)


def clear_service_cache() -> None:
    get_analog_matching_service.cache_clear()
