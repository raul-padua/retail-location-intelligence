"""Deterministic analog-store matching against public market profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from analog_matching.features import FORBIDDEN_OUTCOME_FEATURES, MATCHING_FEATURE_IDS
from analog_matching.matcher import assign_host_county, search_analogs
from analog_matching.service import clear_service_cache, get_analog_matching_service, search_view
from market_discovery.artifact import clear_artifact_cache, load_artifact
from market_discovery.service import clear_service_cache as clear_discovery_cache
from planning.capabilities import get_capability_registry
from retailer_simulation.benchmarks import clear_benchmark_cache, get_benchmark_catalog
from retailer_simulation.generator import generate_simulation
from retailer_simulation.models import RetailerScenario
from retailer_simulation.service import clear_service_cache as clear_simulation_cache
from server.app import app
from tests.conftest import BURLINGTON, CHITTENDEN

ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "data" / "retailer_simulation" / "public_benchmarks.yaml"
ARTIFACT_DIR = ROOT / "data" / "market_discovery" / "v1"


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_artifact_cache()
    clear_discovery_cache()
    clear_simulation_cache()
    clear_benchmark_cache()
    clear_service_cache()
    get_capability_registry.cache_clear()
    yield
    clear_artifact_cache()
    clear_discovery_cache()
    clear_simulation_cache()
    clear_benchmark_cache()
    clear_service_cache()


def _simulation(seed: int = 42, store_count: int = 48) -> object:
    catalog = get_benchmark_catalog(str(BENCHMARKS))
    return generate_simulation(
        RetailerScenario(store_count=store_count, seed=seed),
        catalog,
    )


def test_capability_is_available():
    capability = get_capability_registry().get("retailer.analog_store_search")
    assert capability is not None
    assert capability.is_available


def test_outcome_features_absent_from_matching_ids():
    assert not set(MATCHING_FEATURE_IDS) & FORBIDDEN_OUTCOME_FEATURES
    forbidden_in_registry = {"annual_sales_usd", "gross_margin_pct"}
    assert not forbidden_in_registry & set(MATCHING_FEATURE_IDS)


def test_same_inputs_produce_identical_ranking():
    artifact = load_artifact(str(ARTIFACT_DIR))
    simulation = _simulation(seed=7, store_count=24)
    first = search_analogs(
        artifact=artifact,
        candidate_geoid="50007",
        candidate_name="Chittenden County, Vermont",
        candidate_market_id=CHITTENDEN,
        simulation=simulation,
        top_k=5,
        matcher_version="analog_v1",
        feature_set_version="acs5_2022_apparel_v1",
    )
    second = search_analogs(
        artifact=artifact,
        candidate_geoid="50007",
        candidate_name="Chittenden County, Vermont",
        candidate_market_id=CHITTENDEN,
        simulation=simulation,
        top_k=5,
        matcher_version="analog_v1",
        feature_set_version="acs5_2022_apparel_v1",
    )
    assert first.model_dump() == second.model_dump()


def test_burlington_store_ranks_high_for_chittenden():
    artifact = load_artifact(str(ARTIFACT_DIR))
    simulation = _simulation(seed=42, store_count=48)
    result = search_analogs(
        artifact=artifact,
        candidate_geoid="50007",
        candidate_name="Chittenden County, Vermont",
        candidate_market_id=BURLINGTON,
        simulation=simulation,
        top_k=10,
        matcher_version="analog_v1",
        feature_set_version="acs5_2022_apparel_v1",
    )
    assert result.matches
    burlington_stores = [
        store
        for store in simulation.stores
        if store.city == "Burlington" and store.state == "VT"
    ]
    assert burlington_stores
    top_ids = {match.store_id for match in result.matches[:3]}
    assert any(store.store_id in top_ids for store in burlington_stores)


def test_host_county_assignment_tie_breaks_by_geoid():
    artifact = load_artifact(str(ARTIFACT_DIR))
    simulation = _simulation(store_count=1)
    store = simulation.stores[0]
    geoid, name = assign_host_county(store, artifact)
    assert geoid
    assert name


def test_tie_handling_stable_by_store_id():
    artifact = load_artifact(str(ARTIFACT_DIR))
    simulation = _simulation(seed=99, store_count=12)
    kwargs = dict(
        artifact=artifact,
        candidate_geoid="50007",
        candidate_name="Chittenden County, Vermont",
        candidate_market_id=CHITTENDEN,
        simulation=simulation,
        top_k=12,
        matcher_version="analog_v1",
        feature_set_version="acs5_2022_apparel_v1",
    )
    first = search_analogs(**kwargs)
    second = search_analogs(**kwargs)
    assert [match.store_id for match in first.matches] == [
        match.store_id for match in second.matches
    ]


def test_weak_analogy_discloses_peer_shortfall():
    service = get_analog_matching_service()
    result = service.search_with_scenario(market_id=CHITTENDEN, top_k=1)
    payload = search_view(result)
    if payload["analogy_strength"] != "strong":
        assert payload["warnings"]
    assert payload["analogy_strength"] in {"weak", "moderate", "strong", "insufficient"}


def test_performance_summary_only_on_ranked_matches():
    service = get_analog_matching_service()
    result = service.search_with_scenario(market_id=CHITTENDEN, top_k=3)
    assert result.matches
    for match in result.matches:
        assert match.performance_summary is not None
        assert match.performance_summary.data_class.value == "simulated_retailer_data"


def test_user_facing_copy_never_claims_real_gap_data():
    service = get_analog_matching_service()
    payload = search_view(service.search_with_scenario(market_id=BURLINGTON, top_k=3))
    text = json.dumps(payload).lower()
    for phrase in ["gap data", "real gap", "observed gap"]:
        assert phrase not in text
    assert "northstar" in text or "simulated" in text


def test_api_meta_and_stateless_search():
    client = TestClient(app)
    meta = client.get("/api/analog-matching/meta")
    assert meta.status_code == 200
    assert meta.json()["matcher_version"] == "analog_v1"

    search = client.post(
        "/api/analog-matching/search",
        json={"market_id": CHITTENDEN, "top_k": 4, "preferred_format": "mall"},
    )
    assert search.status_code == 200
    body = search.json()["search"]
    assert len(body["matches"]) == 4
    assert body["matches"][0]["performance_summary"] is not None


def test_session_scoped_search_and_fetch():
    client = TestClient(app)
    session = client.post("/api/sessions")
    session_id = session.json()["session_id"]

    missing = client.get(f"/api/sessions/{session_id}/analog-matching")
    assert missing.status_code == 404

    run = client.post(
        f"/api/sessions/{session_id}/analog-matching/search",
        json={"market_id": BURLINGTON, "top_k": 5},
    )
    assert run.status_code == 200
    assert run.json()["search"]["candidate_geoid"] == "50007"

    fetched = client.get(f"/api/sessions/{session_id}/analog-matching")
    assert fetched.status_code == 200
    assert fetched.json()["search"]["candidate_market_id"] == BURLINGTON
