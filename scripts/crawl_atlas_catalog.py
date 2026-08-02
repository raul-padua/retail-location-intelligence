"""Crawl the public StateBook Calypso topic configuration to enumerate candidate datapoints.

The Atlas documentation states that the published list of datapoints is "[URL to be
determined]", so the topic configuration served alongside the JavaScript display API is the
only machine-readable enumeration available.

In that configuration a `category` is a datapoint *prefix* (for example
`dem.acs.hhd.mdinc`) and `metrics` are the suffixes that may be appended to it (`val`,
`ayc`, `aycp`, `moe`). A full datapoint identifier is `<category>.<metric>`. Derived
metrics written as function calls (for example `cv(val, moe)`) are computed client-side by
Calypso and are not Atlas datapoints, so they are skipped.

This script only *discovers candidates*. Nothing here is trusted as a metric:
`scripts/verify_datapoints.py` promotes a candidate to a verified metric by confirming that
Atlas actually returns a value and metadata for it.

Usage:
    uv run python scripts/crawl_atlas_catalog.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_ROOT = "https://api.statebook.com/api/v1/config"
OUT_DIR = Path(__file__).resolve().parents[1] / "data"

PREFIX_RE = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9_]+){1,6}$")
SIMPLE_METRIC_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def fetch_json(url: str, attempts: int = 3) -> Any | None:
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "retail-location-intelligence/0.1"})
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == attempts - 1:
                return None
        except (URLError, json.JSONDecodeError, TimeoutError):
            if attempt == attempts - 1:
                return None
        time.sleep(0.5 * (attempt + 1))
    return None


def collect_topic_ids(node: Any, topic_ids: set[str]) -> None:
    if isinstance(node, dict):
        for topic in node.get("topics", []) or []:
            if isinstance(topic, dict) and isinstance(topic.get("id"), str):
                topic_ids.add(topic["id"])
        for value in node.values():
            collect_topic_ids(value, topic_ids)
    elif isinstance(node, list):
        for entry in node:
            collect_topic_ids(entry, topic_ids)


def harvest(node: Any, catalog: dict[str, dict[str, Any]], context: dict[str, str]) -> None:
    """Record every (category prefix -> metric suffix) pair found in a topic config."""
    if isinstance(node, dict):
        context = dict(context)
        for key in ("menu", "subject", "collection"):
            if isinstance(node.get(key), str):
                context[key] = node[key]

        categories: list[str] = []
        if isinstance(node.get("category"), str) and PREFIX_RE.match(node["category"]):
            categories.append(node["category"])
        for entry in node.get("categories", []) or []:
            if isinstance(entry, str) and PREFIX_RE.match(entry):
                categories.append(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("category"), str):
                if PREFIX_RE.match(entry["category"]):
                    categories.append(entry["category"])

        metrics = [m for m in (node.get("metrics") or []) if isinstance(m, str) and SIMPLE_METRIC_RE.match(m)]

        for category in categories:
            record = catalog.setdefault(category, {"metrics": set(), "labels": set(), "collection": None})
            record["metrics"].update(metrics)
            for key in ("subject", "menu"):
                if context.get(key):
                    record["labels"].add(context[key])
            if context.get("collection"):
                record["collection"] = context["collection"]

        # A dict-form category entry may carry its own metrics list.
        for entry in node.get("categories", []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("category"), str):
                own = [m for m in (entry.get("metrics") or []) if isinstance(m, str) and SIMPLE_METRIC_RE.match(m)]
                if own and entry["category"] in catalog:
                    catalog[entry["category"]]["metrics"].update(own)

        for value in node.values():
            harvest(value, catalog, context)
    elif isinstance(node, list):
        for entry in node:
            harvest(entry, catalog, context)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    topic_ids: set[str] = set()
    for topicset_name in ("default", "categories"):
        topicset = fetch_json(f"{CONFIG_ROOT}/topicsets/{topicset_name}.json")
        if topicset is None:
            print(f"warning: could not fetch topicset {topicset_name}", file=sys.stderr)
            continue
        collect_topic_ids(topicset, topic_ids)

    print(f"discovered {len(topic_ids)} topic ids")

    catalog: dict[str, dict[str, Any]] = {}
    topics_fetched = 0
    for topic_id in sorted(topic_ids):
        topic = fetch_json(f"{CONFIG_ROOT}/topics/{topic_id}.json")
        if topic is None:
            continue
        topics_fetched += 1
        harvest(topic, catalog, {"topic_id": topic_id})

    candidates: dict[str, dict[str, Any]] = {}
    for category, record in catalog.items():
        metrics = record["metrics"] or {"val"}
        for metric in sorted(metrics):
            candidates[f"{category}.{metric}"] = {
                "category": category,
                "metric": metric,
                "labels": sorted(record["labels"]),
                "collection": record["collection"],
            }

    print(
        f"fetched {topics_fetched} topic configs; "
        f"{len(catalog)} categories -> {len(candidates)} candidate datapoints"
    )

    out_path = OUT_DIR / "atlas_candidate_datapoints.json"
    out_path.write_text(json.dumps(dict(sorted(candidates.items())), indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
