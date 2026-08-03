# Analog matching

Look-alike **NorthStar** stores for a candidate market using **public ACS features only**.

| Piece | Role |
| --- | --- |
| `features.py` | Matching-feature registry + fixed weights (no sales/margin) |
| `matcher.py` | Host-county assignment, distance, ranking, post-rank performance attach |
| `service.py` | Search API over simulation + market-discovery artifacts |

Capability: `retailer.analog_store_search`. Matching inputs: `PUBLIC_MARKET_DATA`.
Performance summaries (after ranking only): `SIMULATED_RETAILER_DATA`.

Docs: [`docs/analog_matching.md`](../docs/analog_matching.md).
