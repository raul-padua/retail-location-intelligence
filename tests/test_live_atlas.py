"""Integration tests against the real StateBook Atlas API.

Deselected by default. Run them with:

    uv run pytest -m live

They exist to catch the failure the mocked tests cannot: Atlas changing its response
shape, retiring a datapoint, or altering the demo token's footprint.
"""

from __future__ import annotations

import pytest

from api.client import AtlasClient, AtlasHTTPError
from api.parsing import parse_getdata
from core.config import get_settings
from metrics.registry import get_registry
from orchestration.pipeline import AnalysisPipeline, AnalysisRequest

pytestmark = pytest.mark.live

BURLINGTON = "city:burlington-vt"
WINOOSKI = "city:winooski-vt"
CHITTENDEN = "county:chittenden-county-vt"


@pytest.fixture(scope="module")
def live_settings():
    settings = get_settings()
    if not settings.atlas_token:
        pytest.skip("STATEBOOK_API_TOKEN is not configured")
    return settings


def test_documented_example_still_returns_a_population(live_settings):
    with AtlasClient(live_settings) as client:
        body, call = client.get_data(["dem.acs.pop.total.val"], [BURLINGTON])

    assert call.status_code == 200
    observation = parse_getdata(body).latest(BURLINGTON, "dem.acs.pop.total.val")
    assert observation is not None
    assert isinstance(observation.value, float) and observation.value > 0
    assert observation.period and observation.source


def test_every_registry_datapoint_still_resolves(live_settings):
    """The registry must not drift away from what Atlas actually serves."""
    registry = get_registry()
    scalar = [m for m in registry.all() if not m.is_collection_metric]

    with AtlasClient(live_settings) as client:
        body, _ = client.get_data(
            sorted({m.atlas_datapoint for m in scalar}), [BURLINGTON, WINOOSKI]
        )
    parsed = parse_getdata(body)

    unresolved = [
        metric.atlas_datapoint
        for metric in scalar
        if parsed.latest(BURLINGTON, metric.atlas_datapoint) is None
    ]
    assert not unresolved, f"registry datapoints no longer served by Atlas: {unresolved}"


def test_collection_metrics_still_resolve(live_settings):
    registry = get_registry()
    collection_metrics = [m for m in registry.all() if m.is_collection_metric]
    if not collection_metrics:
        pytest.skip("no collection metrics in the registry")

    with AtlasClient(live_settings) as client:
        body, _ = client.get_collection(
            collection_metrics[0].atlas_collection,
            sorted({m.atlas_datapoint for m in collection_metrics}),
            [CHITTENDEN],
            item_datapoint=collection_metrics[0].atlas_item_datapoint,
            item_codes=sorted({m.atlas_item_code for m in collection_metrics if m.atlas_item_code}),
        )
    parsed = parse_getdata(body)

    for metric in collection_metrics:
        observation = parsed.latest(CHITTENDEN, metric.atlas_datapoint, item=metric.atlas_item_code)
        assert observation is not None, metric.metric_id
        assert observation.value is not None


def test_atlas_rejects_a_fabricated_datapoint(live_settings):
    """Atlas itself is the last line of defence against an invented identifier."""
    with AtlasClient(live_settings) as client:
        with pytest.raises(AtlasHTTPError) as exc:
            client.get_data(["dem.acs.foot.traffic.val"], [BURLINGTON])
    assert "unknown datapoint" in str(exc.value).lower()


def test_unlicensed_geography_is_refused_by_atlas(live_settings):
    if not live_settings.is_demo_token:
        pytest.skip("only meaningful with the restricted demo token")
    with AtlasClient(live_settings) as client:
        with pytest.raises(AtlasHTTPError):
            client.get_data(["dem.acs.pop.total.val"], ["city:boston-ma"])


def test_full_pipeline_against_live_atlas(live_settings):
    result = AnalysisPipeline(settings=live_settings).run(
        AnalysisRequest(
            question="Which of these regions is most attractive for a new apparel store?",
            geographies=[BURLINGTON, "city:south-burlington-vt", WINOOSKI],
            use_llm_narrative=False,
        )
    )

    assert not result.refused, result.refusal.reason if result.refusal else ""
    assert result.recommendation is not None
    assert result.reproducibility_hash

    # Every usable value must name a real Atlas call.
    call_ids = {call.call_id for call in result.evidence.raw_calls}
    for item in result.evidence.usable_items():
        assert item.call_id in call_ids
        assert item.period and item.source

    # No credential may reach the persisted request/response records. The token value
    # itself is not searched for, because the demo token is the word "demo", which occurs
    # legitimately in explanatory prose; what matters is that no auth field survives.
    for call in result.evidence.raw_calls:
        recorded = call.model_dump_json().lower()
        assert "authorization" not in recorded
        assert "bearer " not in recorded
        assert "auth=" not in recorded
