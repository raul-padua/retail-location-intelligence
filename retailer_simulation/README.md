# Retailer simulation

Seeded, equation-based **NorthStar Apparel** twin for demos. Not observed retailer data.

| Piece | Role |
| --- | --- |
| `benchmarks.py` | Public anchors with VERIFIED / DEMO_DEFAULT / UNVERIFIED_DISABLED |
| `generator.py` | Deterministic stores, monthly, segments |
| `reconciliation.py` | Target vs generated tolerances |
| `enrichment.py` | Host-county / archetype labels for similar-market profiles |
| `service.py` | Run + wire projection |

Capability: `retailer.scenario_simulation`. Data class: `SIMULATED_RETAILER_DATA`
(benchmarks may be `PUBLIC_COMPANY_BENCHMARK`).

Docs: [`docs/synthetic_retailer.md`](../docs/synthetic_retailer.md),
[`docs/data_provenance.md`](../docs/data_provenance.md).  
Catalog: `data/retailer_simulation/public_benchmarks.yaml`.
