"""Shared fixtures.

Integration tests run the real pipeline against a mocked Atlas transport, so they exercise
the client, parser, validator, scorer, and narrator together without touching the network.
Tests marked ``live`` are the only ones that call the real API.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from api.client import AtlasClient
from core.config import Settings
from metrics.registry import MetricRegistry, get_registry
from models.geography import Geography

BURLINGTON = "city:burlington-vt"
SOUTH_BURLINGTON = "city:south-burlington-vt"
WINOOSKI = "city:winooski-vt"
WILLISTON = "city:williston-vt"
CHITTENDEN = "county:chittenden-county-vt"
FRANKLIN = "county:franklin-county-vt"
GRAND_ISLE = "county:grand-isle-county-vt"

# Values approximating what Atlas returns for the demo footprint. Exact figures do not
# matter to these tests; the relationships between them do.
SCALAR_FIXTURE: dict[str, dict[str, float]] = {
    "dem.acs.pop.total.val": {
        BURLINGTON: 44675.0,
        SOUTH_BURLINGTON: 20292.0,
        WINOOSKI: 7997.0,
        WILLISTON: 10169.0,
    },
    "dem.acs.hhd.total.val": {
        BURLINGTON: 17504.0,
        SOUTH_BURLINGTON: 8642.0,
        WINOOSKI: 3499.0,
        WILLISTON: 4108.0,
    },
    "wkf.acs.emp.16pl.labor.civ.total.val": {
        BURLINGTON: 26390.0,
        SOUTH_BURLINGTON: 11840.0,
        WINOOSKI: 5382.0,
        WILLISTON: 6153.0,
    },
    "dem.acs.mdage.total.val": {
        BURLINGTON: 26.8,
        SOUTH_BURLINGTON: 37.9,
        WINOOSKI: 32.1,
        WILLISTON: 40.2,
    },
    "edu.acs.att.25pl.bachpl.pct": {
        BURLINGTON: 0.5723,
        SOUTH_BURLINGTON: 0.6011,
        WINOOSKI: 0.4402,
        WILLISTON: 0.6288,
    },
    "edu.acs.enr.3pl.ugrad.pct": {
        BURLINGTON: 0.2953,
        SOUTH_BURLINGTON: 0.1102,
        WINOOSKI: 0.0904,
        WILLISTON: 0.0611,
    },
    "dem.acs.hhd.mdinc.val": {
        BURLINGTON: 71109.0,
        SOUTH_BURLINGTON: 92338.0,
        WINOOSKI: 73450.0,
        WILLISTON: 118750.0,
    },
    "dem.acs.hhd.pcinc.val": {
        BURLINGTON: 40192.0,
        SOUTH_BURLINGTON: 51204.0,
        WINOOSKI: 41988.0,
        WILLISTON: 62011.0,
    },
    "wkf.acs.emp.16pl.labor.civ.emp.pct": {
        BURLINGTON: 0.9570,
        SOUTH_BURLINGTON: 0.9788,
        WINOOSKI: 0.9702,
        WILLISTON: 0.9812,
    },
    "trn.acs.cmt.mean.val": {
        BURLINGTON: 18.667,
        SOUTH_BURLINGTON: 19.902,
        WINOOSKI: 20.114,
        WILLISTON: 22.336,
    },
    "dem.acs.pop.total.aycp": {
        BURLINGTON: 0.0119,
        SOUTH_BURLINGTON: 0.0221,
        WINOOSKI: 0.0187,
        WILLISTON: 0.0164,
    },
    "dem.acs.hhd.total.aycp": {
        BURLINGTON: 0.0200,
        SOUTH_BURLINGTON: 0.0244,
        WINOOSKI: 0.0155,
        WILLISTON: 0.0198,
    },
    "dem.acs.hhd.mdinc.aycp": {
        BURLINGTON: 0.0643,
        SOUTH_BURLINGTON: 0.0512,
        WINOOSKI: 0.0704,
        WILLISTON: 0.0488,
    },
}

# County-level values so mixed-geography scenarios have something to compare.
COUNTY_FIXTURE: dict[str, dict[str, float]] = {
    "dem.acs.pop.total.val": {CHITTENDEN: 168323.0, FRANKLIN: 50897.0, GRAND_ISLE: 7305.0},
    "dem.acs.hhd.total.val": {CHITTENDEN: 68120.0, FRANKLIN: 20114.0, GRAND_ISLE: 3221.0},
    "wkf.acs.emp.16pl.labor.civ.total.val": {
        CHITTENDEN: 96780.0,
        FRANKLIN: 27455.0,
        GRAND_ISLE: 3908.0,
    },
    "dem.acs.mdage.total.val": {CHITTENDEN: 37.4, FRANKLIN: 41.9, GRAND_ISLE: 49.2},
    "edu.acs.att.25pl.bachpl.pct": {CHITTENDEN: 0.5188, FRANKLIN: 0.2951, GRAND_ISLE: 0.3612},
    "edu.acs.enr.3pl.ugrad.pct": {CHITTENDEN: 0.1204, FRANKLIN: 0.0402, GRAND_ISLE: 0.0311},
    "dem.acs.hhd.mdinc.val": {CHITTENDEN: 89422.0, FRANKLIN: 76310.0, GRAND_ISLE: 82115.0},
    "dem.acs.hhd.pcinc.val": {CHITTENDEN: 48211.0, FRANKLIN: 38104.0, GRAND_ISLE: 42990.0},
    "wkf.acs.emp.16pl.labor.civ.emp.pct": {
        CHITTENDEN: 0.9744,
        FRANKLIN: 0.9661,
        GRAND_ISLE: 0.9702,
    },
    "trn.acs.cmt.mean.val": {CHITTENDEN: 20.41, FRANKLIN: 27.88, GRAND_ISLE: 31.12},
    "dem.acs.pop.total.aycp": {CHITTENDEN: 0.0093, FRANKLIN: 0.0071, GRAND_ISLE: 0.0055},
    "dem.acs.hhd.total.aycp": {CHITTENDEN: 0.0148, FRANKLIN: 0.0122, GRAND_ISLE: 0.0104},
    "dem.acs.hhd.mdinc.aycp": {CHITTENDEN: 0.0571, FRANKLIN: 0.0488, GRAND_ISLE: 0.0502},
}

for _datapoint, _table in COUNTY_FIXTURE.items():
    SCALAR_FIXTURE.setdefault(_datapoint, {}).update(_table)

DEFAULT_PERIOD = "2024"
DEFAULT_SOURCE = "acs5"


def build_getdata_response(
    datapoints: list[str],
    geographies: list[str],
    *,
    values: dict[str, dict[str, float]] | None = None,
    periods: dict[str, dict[str, str]] | None = None,
    sources: dict[str, dict[str, str]] | None = None,
    reported_geographies: dict[str, dict[str, str]] | None = None,
    omit: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a documented-shape Atlas response.

    ``omit`` drops specific ``(datapoint, geography)`` pairs to simulate missing data.
    """
    values = values or SCALAR_FIXTURE
    omit = omit or set()

    def block(geography: str) -> dict[str, Any]:
        data = []
        for datapoint in datapoints:
            if (datapoint, geography) in omit:
                continue
            table = values.get(datapoint, {})
            if geography not in table:
                continue
            entry: dict[str, Any] = {
                "datapoint": datapoint,
                "period": (periods or {}).get(datapoint, {}).get(geography, DEFAULT_PERIOD),
                "source": (sources or {}).get(datapoint, {}).get(geography, DEFAULT_SOURCE),
                "value": table[geography],
            }
            reported = (reported_geographies or {}).get(datapoint, {}).get(geography)
            if reported:
                entry["geography"] = reported
            data.append(entry)
        return {"geography": geography, "data": data}

    if len(geographies) == 1:
        resultset: dict[str, Any] = block(geographies[0])
    else:
        resultset = {"geographies": [block(geography) for geography in geographies]}

    return {
        "resultset": resultset,
        "metadata": {
            "datapoints": {
                datapoint: {"description": datapoint, "attribution": "US Census, ACS"}
                for datapoint in datapoints
            }
        },
        "status": {"id": "test", "version": "1.0.0"},
    }


def build_collection_response(geographies: list[str], parent: str) -> dict[str, Any]:
    """CBP-style collection response where every city resolves to one parent county."""

    def block(geography: str) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "collection": "ind.cbp.naics",
            "items": [
                {
                    "item": "44",
                    "period": "2023",
                    "data": [
                        {"datapoint": "ind.cbp.naics.est.val", "value": 734},
                    ],
                },
                {
                    "item": "722",
                    "period": "2023",
                    "data": [
                        {"datapoint": "ind.cbp.naics.est.val", "value": 423},
                    ],
                },
            ],
        }
        if geography != parent:
            entry["geography"] = parent
        return {"geography": geography, "data": [entry]}

    return {
        "resultset": {"geographies": [block(geography) for geography in geographies]},
        "metadata": {},
        "status": {"id": "test", "version": "1.0.0"},
    }


ResponseBuilder = Callable[[dict[str, Any]], httpx.Response]


def make_transport(builder: ResponseBuilder) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        return builder(body)

    return httpx.MockTransport(handler)


def default_builder(
    *,
    omit: set[tuple[str, str]] | None = None,
    periods: dict[str, dict[str, str]] | None = None,
    sources: dict[str, dict[str, str]] | None = None,
    collection_parent: str = "county:chittenden-county-vt",
) -> ResponseBuilder:
    """Respond to both scalar and collection requests using the fixture values."""

    def builder(body: dict[str, Any]) -> httpx.Response:
        data = body.get("data", {})
        criteria = body.get("criteria", {})
        geographies = criteria.get("geographies") or (
            [criteria["geography"]] if "geography" in criteria else []
        )

        if data.get("collections"):
            return httpx.Response(
                200, json=build_collection_response(geographies, collection_parent)
            )

        datapoints = data.get("datapoints", [])
        return httpx.Response(
            200,
            json=build_getdata_response(
                datapoints, geographies, omit=omit, periods=periods, sources=sources
            ),
        )

    return builder


@pytest.fixture
def settings() -> Settings:
    return Settings(
        atlas_token="test-token",
        atlas_base_url="https://api.statebook.test",
        timeout_seconds=5.0,
        max_retries=1,
        openai_api_key=None,
        llm_model="none",
        log_level="WARNING",
    )


@pytest.fixture
def registry() -> MetricRegistry:
    return get_registry()


@pytest.fixture
def client_factory(settings: Settings):
    """Build an ``AtlasClient`` bound to a mock transport."""

    def factory(builder: ResponseBuilder):
        return lambda: AtlasClient(settings, transport=make_transport(builder))

    return factory


@pytest.fixture
def geographies() -> list[Geography]:
    return [Geography.parse(slug) for slug in (BURLINGTON, SOUTH_BURLINGTON, WINOOSKI)]
