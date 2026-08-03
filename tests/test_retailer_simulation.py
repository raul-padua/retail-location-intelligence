"""Deterministic NorthStar Apparel fictional retailer simulation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from models.provenance import DataClass
from planning.capabilities import get_capability_registry
from retailer_simulation.benchmarks import (
    active_benchmarks,
    clear_benchmark_cache,
    get_benchmark_catalog,
    load_benchmark_catalog,
)
from retailer_simulation.generator import generate_simulation
from retailer_simulation.models import RetailerScenario, VerificationState
from retailer_simulation.service import clear_service_cache, get_retailer_simulation_service
from server.app import app

ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "data" / "retailer_simulation" / "public_benchmarks.yaml"


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_benchmark_cache()
    clear_service_cache()
    get_capability_registry.cache_clear()
    yield
    clear_benchmark_cache()
    clear_service_cache()


def test_capability_is_available():
    capability = get_capability_registry().get("retailer.scenario_simulation")
    assert capability is not None
    assert capability.is_available


def test_disabled_benchmarks_are_excluded_from_generation():
    catalog = load_benchmark_catalog(BENCHMARKS)
    disabled = [
        benchmark.metric
        for benchmark in catalog.benchmarks
        if benchmark.verification_state is VerificationState.UNVERIFIED_DISABLED
    ]
    assert disabled
    active_metrics = {benchmark.metric for benchmark in active_benchmarks(catalog)}
    for metric in disabled:
        assert metric not in active_metrics


def test_same_seed_produces_identical_outputs():
    catalog = get_benchmark_catalog(str(BENCHMARKS))
    scenario = RetailerScenario(store_count=24, seed=7, sales_target_usd=120_000_000)
    first = generate_simulation(scenario, catalog)
    second = generate_simulation(scenario, catalog)
    assert first.model_dump() == second.model_dump()


def test_different_seed_produces_different_valid_outputs():
    catalog = get_benchmark_catalog(str(BENCHMARKS))
    base = RetailerScenario(store_count=24, seed=7, sales_target_usd=120_000_000)
    other = RetailerScenario(store_count=24, seed=8, sales_target_usd=120_000_000)
    first = generate_simulation(base, catalog)
    second = generate_simulation(other, catalog)
    assert first.model_dump() != second.model_dump()
    assert first.reconciliation_passed
    assert second.reconciliation_passed


def test_reconciliation_passes_and_no_negatives():
    catalog = get_benchmark_catalog(str(BENCHMARKS))
    artifact = generate_simulation(RetailerScenario(), catalog)
    assert artifact.reconciliation_passed
    assert all(store.annual_sales_usd >= 0 for store in artifact.stores)
    assert all(store.gross_margin_pct >= 0 for store in artifact.stores)
    assert all(store.sq_ft >= 0 for store in artifact.stores)
    sales_line = next(
        line for line in artifact.reconciliation if line.metric == "total_annual_sales_usd"
    )
    assert sales_line.passed


def test_provenance_survives_serialization():
    service = get_retailer_simulation_service(str(BENCHMARKS))
    payload = service.run_view(RetailerScenario(store_count=12, seed=3))
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["data_class"]["data_class"] == DataClass.SIMULATED_RETAILER_DATA
    assert decoded["stores"][0]["data_class"]["data_class"] == DataClass.SIMULATED_RETAILER_DATA
    assert decoded["scenario"]["data_class"]["data_class"] == DataClass.USER_ASSUMPTION


def test_user_facing_copy_never_claims_real_gap_data():
    service = get_retailer_simulation_service(str(BENCHMARKS))
    payload = service.run_view(RetailerScenario(store_count=8, seed=99))
    text = json.dumps(payload).lower()
    forbidden = ["gap data", "real gap", "observed gap", "actual gap store"]
    for phrase in forbidden:
        assert phrase not in text
    assert "northstar apparel" in text
    assert "simulated" in payload["data_class"]["label"].lower()


def test_api_lists_benchmarks_and_runs_stateless():
    client = TestClient(app)
    benchmarks = client.get("/api/retailer-simulation/benchmarks")
    assert benchmarks.status_code == 200
    body = benchmarks.json()
    assert body["disabled_count"] >= 1
    assert any(
        entry["verification_state"] == "UNVERIFIED_DISABLED"
        for entry in body["benchmarks"]
    )

    run = client.post(
        "/api/retailer-simulation/run",
        json={"store_count": 10, "seed": 42, "sales_target_usd": 50_000_000},
    )
    assert run.status_code == 200
    simulation = run.json()["simulation"]
    assert simulation["reconciliation_passed"]
    assert len(simulation["stores"]) == 10
    assert all(store.get("host_geoid") for store in simulation["stores"])
    assert all(store.get("host_cluster_id") for store in simulation["stores"])


def test_similar_market_profile_for_selected_candidate():
    service = get_retailer_simulation_service(str(BENCHMARKS))
    payload = service.run_view(
        RetailerScenario(store_count=24, seed=7),
        focus_market_id="city:burlington-vt",
    )
    profile = payload["similar_market_profile"]
    assert profile is not None
    assert profile["cluster_id"]
    assert profile["data_class"]["data_class"] == DataClass.SIMULATED_RETAILER_DATA
    assert "forecast" not in profile["note"].lower() or "not a forecast" in profile["note"].lower()


def test_session_scoped_run_and_fetch():
    client = TestClient(app)
    session = client.post("/api/sessions")
    assert session.status_code == 201
    session_id = session.json()["session_id"]

    missing = client.get(f"/api/sessions/{session_id}/retailer-simulation")
    assert missing.status_code == 404

    run = client.post(
        f"/api/sessions/{session_id}/retailer-simulation/run",
        json={"store_count": 6, "seed": 11, "sales_target_usd": 30_000_000},
    )
    assert run.status_code == 200

    fetched = client.get(f"/api/sessions/{session_id}/retailer-simulation")
    assert fetched.status_code == 200
    assert fetched.json()["simulation"]["seed"] == 11
    assert len(fetched.json()["simulation"]["stores"]) == 6
