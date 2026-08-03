# Data provenance

Every analytical value in this prototype carries an explicit **data class** so Atlas
evidence, public market data, simulated retailer outputs, and user assumptions cannot be
silently mixed in charts or narratives.

## DataClass enum

Defined in `models/provenance.py` and projected on the wire as labeled badges.

| Class | Label | Meaning |
| --- | --- | --- |
| `atlas_evidence` | Atlas verified | Returned by the StateBook Atlas API |
| `public_market_data` | Public market data | Government or licensed open data (e.g. ACS county features) |
| `public_company_benchmark` | Public company benchmark | Aggregate figure from a public filing or official company site |
| `simulated_retailer_data` | Simulated | Seeded simulator output; not observed retailer performance |
| `user_supplied_proprietary_data` | Proprietary (user) | Reserved for future proprietary ingestion |
| `user_assumption` | User assumption | Stated by the user; not measured |
| `agent_interpretation` | Agent interpretation | Planner or assistant wording; not a data value |

## Phase 2 — public market archetypes

- County clustering artifact: `public_market_data`
- See `docs/market_discovery.md`

## Phase 3 — NorthStar Apparel simulation

- **Benchmark anchors** (`data/retailer_simulation/public_benchmarks.yaml`): `public_company_benchmark`
- **Verification states** on benchmarks: `VERIFIED`, `DEMO_DEFAULT`, `UNVERIFIED_DISABLED`
  - Disabled entries are catalogued but excluded from generation
- **Scenario parameters** (store count, format mix, seed, targets): `user_assumption`
- **Generated stores, monthly roll-ups, segments**: `simulated_retailer_data`

The UI always shows the simulated badge on Phase 3 panels. See `docs/synthetic_retailer.md`.

## Phase 4 — analog store matching

- **Candidate market profile**: `public_market_data` (ACS county features from market discovery)
- **Match vector / contributions**: `public_market_data` only — no sales, margin, or performance
- **Performance summary on ranked matches**: `simulated_retailer_data` (median/IQR of NorthStar stores)
- **Analogy strength / warnings**: derived metadata; not a data value

The UI always shows the simulated badge when displaying performance summaries on the Analog
stores tab. See `docs/analog_matching.md`.

## UI contract

`ProvenanceBadge` maps each class to a tone and short note. Any panel that renders numbers
from more than one class must show the badge for that payload.

## Serialization

Data class survives JSON round-trip on API responses. Tests assert provenance fields on
simulation artifacts after `model_dump` / HTTP projection.
