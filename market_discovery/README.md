# Market discovery

Deterministic **public-county** archetypes. Analytical membership lives here — never in the
TypeScript client.

| Piece | Role |
| --- | --- |
| `features.py` | ACS-shaped feature registry |
| `pipeline.py` | Impute, transform, scale, correlation prune |
| `cluster.py` | K-means + canonical `A0N` ids |
| `artifact.py` / `service.py` | Load versioned artifact; market profile + peers |
| `geography_bridge.py` | Atlas demo slug → county GEOID |

Capability: `market.archetype_analysis`. Data class: `PUBLIC_MARKET_DATA`.

Docs: [`docs/market_discovery.md`](../docs/market_discovery.md),
[`docs/clustering_methodology.md`](../docs/clustering_methodology.md).  
Artifact: `data/market_discovery/v1/`. Build: `uv run python scripts/build_market_discovery_artifact.py`.
