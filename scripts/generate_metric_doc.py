"""Generate docs/metric_registry.md from the live registry and verification record.

The document is generated rather than hand-written so it cannot drift from the code or
claim a datapoint that verification never confirmed.

Usage:
    uv run python scripts/generate_metric_doc.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metrics.registry import MetricRegistry, get_registry  # noqa: E402
from models.metrics import CATEGORY_LABELS, MetricCategory  # noqa: E402
from scoring.service import DEFAULT_CATEGORY_WEIGHTS  # noqa: E402

OUT_PATH = ROOT / "docs" / "metric_registry.md"
CANDIDATES_PATH = ROOT / "data" / "atlas_candidate_datapoints.json"


def main() -> int:
    registry = get_registry()
    verified = MetricRegistry.load_verification_record()
    candidates = (
        json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
        if CANDIDATES_PATH.exists()
        else {}
    )

    lines: list[str] = [
        "# Metric registry",
        "",
        "Every metric below names a StateBook Atlas datapoint that was confirmed to return "
        "a value from the live API. The registry refuses to load if any entry is missing "
        "from `data/atlas_verified_datapoints.json`, so a datapoint identifier that was "
        "never observed cannot enter the scoring model.",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d} by `scripts/generate_metric_doc.py`.",
        "",
        "## How this list was produced",
        "",
        "The Atlas documentation states that the published datapoint list is "
        "\"[URL to be determined]\", so the catalogue was discovered rather than read:",
        "",
        "1. `scripts/crawl_atlas_catalog.py` walks the public Calypso topic configuration "
        "at `https://api.statebook.com/api/v1/config/`, where a *category* is a datapoint "
        "prefix and *metrics* are the suffixes that may be appended to it "
        f"(`val`, `ayc`, `aycp`, `moe`, `pct`). That produced {len(candidates):,} candidate "
        "identifiers.",
        "2. `scripts/verify_datapoints.py` calls the live API for every candidate across a "
        "metro, a county, and two cities of very different size, and records which "
        f"identifiers actually return a value. {len(verified):,} were confirmed.",
        "3. The metrics below were selected from the confirmed set on retail relevance. "
        "Atlas rejects an unknown identifier outright with "
        "`Unknown datapoint specified`, which is the final backstop against a fabricated id.",
        "",
        "## Units",
        "",
        "Atlas returns American Community Survey shares as proportions (`0.9517` for "
        "95.17%), not in the 0-100 form the documentation describes. The registry records "
        "the proportion form and the interface multiplies for display. No conversion "
        "happens before scoring, so normalization operates on the values Atlas returned.",
        "",
        "## Category weights",
        "",
        "Default weights, adjustable in the interface before recalculating:",
        "",
        "| Category | Default weight |",
        "| --- | --- |",
    ]

    for category, weight in DEFAULT_CATEGORY_WEIGHTS.items():
        lines.append(f"| {CATEGORY_LABELS[category]} | {weight:.0%} |")

    lines += [
        "",
        "Within a category, metric weights are relative and are renormalized to sum to 1 "
        "over whichever metrics survived validation for a given region. Across categories, "
        "weights are renormalized over whichever categories produced a score. Both "
        "adjustments are disclosed in the trace panel.",
        "",
        "## Metrics",
        "",
    ]

    for category in MetricCategory:
        metrics = registry.by_category(category)
        if not metrics:
            continue
        lines += [
            f"### {CATEGORY_LABELS[category]} "
            f"(default weight {DEFAULT_CATEGORY_WEIGHTS.get(category, 0):.0%})",
            "",
        ]
        for metric in metrics:
            record = verified.get(metric.atlas_datapoint, {})
            observations = record.get("observations", {})
            example = next(iter(observations.values()), {}) if observations else {}
            identifier = metric.atlas_datapoint + (
                f" (collection `{metric.atlas_collection}`, item `{metric.atlas_item_code}`)"
                if metric.is_collection_metric
                else ""
            )
            lines += [
                f"#### {metric.display_name}",
                "",
                f"- **Atlas identifier**: `{identifier}`",
                f"- **Verified description**: {record.get('description') or 'n/a'}",
                f"- **Attribution**: {record.get('attribution') or metric.source}",
                f"- **Unit**: {metric.unit}",
                f"- **Direction**: {metric.direction.value.replace('_', ' ')}",
                f"- **Weight within category**: {metric.weight}",
                f"- **Normalization**: {metric.normalization}",
                f"- **Observed period**: {example.get('period') or ', '.join(metric.expected_periods) or 'n/a'}",
                f"- **Observed source**: {example.get('source') or 'n/a'}",
                "- **Published at**: "
                + ", ".join(str(level) for level in metric.supported_geography_types),
                f"- **Verified in**: {len(record.get('available_geographies', []))} of the "
                "probed geographies",
                f"- **Why it matters to a retailer**: {metric.retail_rationale}",
            ]
            if metric.notes:
                lines.append(f"- **Caveat**: {metric.notes}")
            lines.append("")

    lines += [
        "## Dimensions that are deliberately absent",
        "",
        "The brief asks for several retail-location dimensions. These were investigated and "
        "excluded because Atlas does not support them at the required resolution, or at all:",
        "",
        "| Dimension | Status |",
        "| --- | --- |",
        "| Population density / land area | No scalar density or land-area datapoint was "
        "confirmed in the verified set, so density could not be derived from Atlas values "
        "alone. Total population is used as the market-size proxy instead. |",
        "| Transportation accessibility (airports, ports) | Available only as point-level "
        "collections (`trn.airport`, `trn.port`) that describe facility attributes rather "
        "than a comparable regional score. Mean commute time is used instead. |",
        "| Commute mode share | `trn.acs.cmt.mode.wkf.*` is a collection keyed by travel "
        "mode. Supported by the client, but not yet reduced to a defensible single "
        "accessibility indicator. |",
        "| Retail and food-service establishments | Included, but published only at county "
        "level and above. Requesting them for a city causes Atlas to answer with the parent "
        "county, which the validation layer detects and excludes. |",
        "| Foot traffic, competitor locations, rent, transaction data | Not present in "
        "Atlas at any resolution. Requests that depend on them are refused. |",
        "",
        "## Regenerating",
        "",
        "```bash",
        "uv run python scripts/crawl_atlas_catalog.py   # discover candidate identifiers",
        "uv run python scripts/verify_datapoints.py     # confirm them against the live API",
        "uv run python scripts/generate_metric_doc.py   # rewrite this document",
        "```",
        "",
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(registry)} metrics)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
