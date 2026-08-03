# Market discovery

Phase 2 adds a **public-county** discovery layer beside Atlas evidence. It answers:
*which kind of U.S. county market is this?* — not *how will a store perform?*

## What is in the artifact

Versioned files under `data/market_discovery/v1/`:

| File | Contents |
|---|---|
| `manifest.json` | Seed, config hash, k, quality, scaler/PCA freeze, feature registry snapshot |
| `counties.json` | County GEOIDs, centroids, raw feature values |
| `assignments.json` | Cluster id, PCA coords, assignment method |
| `clusters.json` | Archetype summaries and distinctive features |

Every payload is labeled `PUBLIC_MARKET_DATA`.

## Feature registry

`market_discovery/features.py` enumerates ACS-shaped features with source URL, period,
transform, missing-data policy, and retail rationale. Clustering may use only these ids.

## Build

```bash
uv run python scripts/build_market_discovery_artifact.py
```

Default source is the offline ACS-shaped fixture (`market_discovery/fixture_counties.py`).
A live Census ACS pull can be wired later (`--source acs`); request-time clustering is
never performed.

## Lookup

- County GEOID (5 digits), or
- Atlas demo city/county slug → parent county via `market_discovery/geography_bridge.py`

CBSA and congressional districts are refused (`422`) rather than guessed.

## Capability

`market.archetype_analysis` — available, deterministic. The agent may request or explain
results; it cannot invent membership.
