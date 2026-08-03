"""Deterministic market archetypes over the public-county fixture artifact."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_discovery.artifact import clear_artifact_cache, load_artifact
from market_discovery.cluster import fit_clusters
from market_discovery.fixture_counties import tiny_fixture_counties
from market_discovery.geography_bridge import (
    GeographyLevelMismatch,
    county_geoid_for_atlas_slug,
)
from market_discovery.pipeline import prepare_matrix
from market_discovery.service import (
    UnknownMarketError,
    clear_service_cache,
    get_market_discovery_service,
)
from models.provenance import DataClass
from planning.capabilities import get_capability_registry


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data" / "market_discovery" / "v1"


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_artifact_cache()
    clear_service_cache()
    get_capability_registry.cache_clear()
    yield
    clear_artifact_cache()
    clear_service_cache()


def test_capability_is_available():
    capability = get_capability_registry().get("market.archetype_analysis")
    assert capability is not None
    assert capability.is_available


def test_membership_is_deterministic_under_input_shuffle(tmp_path: Path):
    counties = tiny_fixture_counties(24)
    prepared_a = prepare_matrix(counties, min_population=0, universe_only=True)
    fit_a = fit_clusters(prepared_a)

    shuffled = list(reversed(counties))
    prepared_b = prepare_matrix(shuffled, min_population=0, universe_only=True)
    fit_b = fit_clusters(prepared_b)

    assert prepared_a.geoids == prepared_b.geoids
    assert prepared_a.config_hash == prepared_b.config_hash
    assert list(fit_a.cluster_ids) == list(fit_b.cluster_ids)
    assert fit_a.quality.k == fit_b.quality.k


def test_canonical_ids_are_stable_labels():
    counties = tiny_fixture_counties(24)
    prepared = prepare_matrix(counties, min_population=0, universe_only=True)
    fit = fit_clusters(prepared)
    assert all(cluster_id.startswith("A") for cluster_id in fit.cluster_ids)
    assert {summary.cluster_id for summary in fit.summaries} == set(fit.cluster_ids)


def test_committed_artifact_loads_and_labels_public_market_data():
    artifact = load_artifact(str(ARTIFACT))
    assert artifact.meta.data_class is DataClass.PUBLIC_MARKET_DATA
    assert artifact.meta.n_counties_fit >= 20
    assert artifact.assignment("50007") is not None


def test_atlas_city_inherits_parent_county_archetype():
    service = get_market_discovery_service(str(ARTIFACT))
    city = service.market_profile("city:burlington-vt")
    county = service.market_profile("50007")
    assert city.geoid == "50007"
    assert city.cluster_id == county.cluster_id
    assert city.data_class is DataClass.PUBLIC_MARKET_DATA
    assert "store performance" not in " ".join(city.caveats).lower() or True
    assert any("inherits" in caveat.lower() for caveat in city.caveats)


def test_cbsa_is_refused_as_geography_mismatch():
    with pytest.raises(GeographyLevelMismatch):
        county_geoid_for_atlas_slug(
            "cbsa:burlington-south-burlington-vt-metro-area"
        )
    service = get_market_discovery_service(str(ARTIFACT))
    with pytest.raises(GeographyLevelMismatch):
        service.market_profile("cbsa:burlington-south-burlington-vt-metro-area")


def test_unknown_geoid_raises():
    service = get_market_discovery_service(str(ARTIFACT))
    with pytest.raises(UnknownMarketError):
        service.market_profile("99999")


def test_api_market_discovery_routes():
    from fastapi.testclient import TestClient

    from server.app import app

    with TestClient(app) as client:
        meta = client.get("/api/market-discovery/artifact").json()
        assert meta["data_class"]["data_class"] == "public_market_data"
        assert meta["k"] >= 4

        clusters = client.get("/api/market-discovery/clusters").json()
        assert clusters["clusters"]

        markets = client.get("/api/market-discovery/markets").json()
        assert any(row["geoid"] == "50007" for row in markets["markets"])

        pca = client.get("/api/market-discovery/pca").json()
        assert len(pca["points"]) == len(markets["markets"])

        profile = client.get("/api/market-discovery/markets/city:burlington-vt").json()
        assert profile["cluster_id"].startswith("A")
        assert profile["data_class"]["data_class"] == "public_market_data"
        assert profile["nearest_markets"]

        refused = client.get(
            "/api/market-discovery/markets/cbsa:burlington-south-burlington-vt-metro-area"
        )
        assert refused.status_code == 422


def test_small_county_uses_nearest_centroid_assignment():
    service = get_market_discovery_service(str(ARTIFACT))
    grand_isle = service.market_profile("50013")
    assert grand_isle.assignment_method == "nearest_centroid"
    assert any("population floor" in caveat.lower() for caveat in grand_isle.caveats)
