"""Verify candidate Atlas datapoints against the live API.

A candidate discovered by ``crawl_atlas_catalog.py`` is only a *claim* that a datapoint
exists. This script is what makes it a fact: it calls Atlas for every demo-licensed
geography and records which datapoints actually return a numeric value, at which period,
from which source, with which description and attribution.

The metric registry refuses to load any metric that is absent from the artifact this
script writes, which is the mechanism that prevents fabricated datapoint identifiers.

Usage:
    uv run python scripts/verify_datapoints.py                 # verify all candidates
    uv run python scripts/verify_datapoints.py --limit 200     # smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.client import AtlasClient, AtlasError  # noqa: E402
from api.geographies import DEMO_GEOGRAPHIES  # noqa: E402
from api.parsing import MalformedAtlasResponse, parse_getdata  # noqa: E402
from core.config import get_settings  # noqa: E402

DATA_DIR = ROOT / "data"
CANDIDATES_PATH = DATA_DIR / "atlas_candidate_datapoints.json"
VERIFIED_PATH = DATA_DIR / "atlas_verified_datapoints.json"

# Representative slice of the demo footprint: one metro, one county, two cities of very
# different size. A datapoint that resolves for all four is safe to compare across the set.
PROBE_GEOGRAPHIES = [
    "cbsa:burlington-south-burlington-vt-metro-area",
    "county:chittenden-county-vt",
    "city:burlington-vt",
    "city:winooski-vt",
]

BATCH_SIZE = 20

# Collection datapoints cannot be probed as scalars, so they are enumerated explicitly.
# Each entry is (collection, item_datapoint, item_codes, datapoints).
COLLECTION_PROBES: list[tuple[str, str, list[str], list[str]]] = [
    (
        "ind.cbp.naics",
        "ind.cbp.naics.code",
        ["44", "45", "722"],
        ["ind.cbp.naics.desc", "ind.cbp.naics.est.val", "ind.cbp.naics.emp.val"],
    ),
]


def probe_batch(
    client: AtlasClient, datapoints: list[str], geographies: list[str]
) -> dict[str, dict[str, Any]] | None:
    """Return per-datapoint results, or None if the whole batch failed."""
    try:
        body, _ = client.get_data(datapoints, geographies, include_metadata=True)
        parsed = parse_getdata(body)
    except (AtlasError, MalformedAtlasResponse):
        return None

    results: dict[str, dict[str, Any]] = {}
    for datapoint in datapoints:
        per_geography: dict[str, Any] = {}
        for geography in geographies:
            observation = parsed.latest(geography, datapoint)
            if observation is None or observation.value is None:
                continue
            per_geography[geography] = {
                "value": observation.value,
                "period": observation.period,
                "source": observation.source,
                "reported_geography": observation.reported_geography,
            }
        if not per_geography:
            continue
        metadata = parsed.datapoint_metadata.get(datapoint, {})
        results[datapoint] = {
            "datapoint": datapoint,
            "description": metadata.get("description"),
            "attribution": metadata.get("attribution"),
            "collection": metadata.get("collection"),
            "observations": per_geography,
            "available_geographies": sorted(per_geography),
            "numeric": all(
                isinstance(entry["value"], (int, float)) for entry in per_geography.values()
            ),
        }
    return results


def probe_collections(
    client: AtlasClient, geographies: list[str]
) -> dict[str, dict[str, Any]]:
    """Verify collection datapoints, recording availability per item code."""
    results: dict[str, dict[str, Any]] = {}

    for collection, item_datapoint, item_codes, datapoints in COLLECTION_PROBES:
        try:
            body, _ = client.get_collection(
                collection,
                datapoints,
                geographies,
                item_datapoint=item_datapoint,
                item_codes=item_codes,
                include_metadata=True,
            )
            parsed = parse_getdata(body)
        except (AtlasError, MalformedAtlasResponse) as exc:
            print(f"  collection {collection} failed: {exc}", file=sys.stderr)
            continue

        for datapoint in datapoints:
            per_geography: dict[str, Any] = {}
            items_seen: set[str] = set()
            for geography in geographies:
                for code in item_codes:
                    observation = parsed.latest(geography, datapoint, item=code)
                    if observation is None or observation.value is None:
                        continue
                    items_seen.add(code)
                    # Record the first available item code per geography; the registry
                    # pins the exact code it needs.
                    if geography not in per_geography:
                        per_geography[geography] = {
                            "value": observation.value,
                            "period": observation.period,
                            "source": observation.source,
                            "reported_geography": observation.reported_geography,
                            "item": code,
                        }
            if not per_geography:
                continue
            metadata = parsed.datapoint_metadata.get(datapoint, {})
            results[datapoint] = {
                "datapoint": datapoint,
                "description": metadata.get("description"),
                "attribution": metadata.get("attribution"),
                "collection": collection,
                "verified_items": sorted(items_seen),
                "observations": per_geography,
                "available_geographies": sorted(per_geography),
                "numeric": all(
                    isinstance(entry["value"], (int, float)) for entry in per_geography.values()
                ),
            }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Only probe the first N candidates")
    parser.add_argument(
        "--collections-only",
        action="store_true",
        help="Probe only collection datapoints and merge them into the existing record",
    )
    parser.add_argument(
        "--geographies",
        nargs="*",
        default=PROBE_GEOGRAPHIES,
        help="Geography slugs to probe",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not CANDIDATES_PATH.exists():
        print(f"error: {CANDIDATES_PATH} not found. Run crawl_atlas_catalog.py first.", file=sys.stderr)
        return 1

    unknown = [slug for slug in args.geographies if slug not in DEMO_GEOGRAPHIES]
    if unknown and settings.is_demo_token:
        print(f"error: not licensed by the demo token: {unknown}", file=sys.stderr)
        return 1

    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    datapoint_ids = [] if args.collections_only else sorted(candidates)
    if args.limit:
        datapoint_ids = datapoint_ids[: args.limit]

    verified: dict[str, dict[str, Any]] = {}
    if args.collections_only and VERIFIED_PATH.exists():
        verified = json.loads(VERIFIED_PATH.read_text(encoding="utf-8"))
        print(f"merging into {len(verified)} previously verified datapoints")

    print(f"probing {len(datapoint_ids)} candidates across {len(args.geographies)} geographies")

    failed_batches = 0

    with AtlasClient(settings) as client:
        for start in range(0, len(datapoint_ids), BATCH_SIZE):
            batch = datapoint_ids[start : start + BATCH_SIZE]
            results = probe_batch(client, batch, args.geographies)

            if results is None:
                # One bad identifier can fail an entire batch, so fall back to singles to
                # avoid discarding the good datapoints alongside it.
                failed_batches += 1
                for datapoint in batch:
                    single = probe_batch(client, [datapoint], args.geographies)
                    if single:
                        verified.update(single)
            else:
                verified.update(results)

            done = min(start + BATCH_SIZE, len(datapoint_ids))
            print(f"  {done}/{len(datapoint_ids)} probed, {len(verified)} verified", flush=True)

        collection_results = probe_collections(client, args.geographies)
        if collection_results:
            print(f"  verified {len(collection_results)} collection datapoint(s)")
        verified.update(collection_results)

    for entry in verified.values():
        entry["labels"] = candidates.get(entry["datapoint"], {}).get("labels", [])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VERIFIED_PATH.write_text(json.dumps(dict(sorted(verified.items())), indent=2), encoding="utf-8")

    numeric = sum(1 for entry in verified.values() if entry["numeric"])
    everywhere = sum(
        1 for entry in verified.values() if len(entry["available_geographies"]) == len(args.geographies)
    )
    print(
        f"\nverified {len(verified)} datapoints "
        f"({numeric} numeric, {everywhere} present in every probed geography); "
        f"{failed_batches} batch(es) needed single-datapoint fallback"
    )
    print(f"wrote {VERIFIED_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
