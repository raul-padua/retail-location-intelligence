# Synthetic retailer simulation (Phase 3)

When a candidate market is selected, a run can also return a **similar-market profile**:
simulated stores hosted in counties that share that candidate’s public-market archetype.
That is demo context for “how fictional stores fare in markets like this,” not a site
forecast. For ranked look-alike stores with feature-level explanations, use Phase 4
analog matching.

NorthStar Apparel is a **fictional** national apparel banner used to make the retail
strategy framing concrete. The Phase 3 simulator generates seeded, equation-based store
networks and roll-ups for demo exploration. It is **never** presented as real GAP or any
other retailer’s observed performance.

## What this is

| Layer | Data class | Role |
| --- | --- | --- |
| Public benchmarks | `public_company_benchmark` | Aggregate anchors from filings or demo defaults |
| Scenario inputs | `user_assumption` | Explicit store count, format mix, seed, sales target, margin range |
| Generated outputs | `simulated_retailer_data` | Stores, monthly totals, segment shares, reconciliation |

The agent may **explain** simulation results and recommend running one, but deterministic
Python services own the math. Scenario parameters must be posted explicitly — the agent
cannot silently change assumptions.

## NorthStar Apparel

- Brand name in all UI copy: **NorthStar Apparel**
- GAP-like framing appears only in docs/README as an illustrative comparison
- User-facing strings must not claim “GAP data” or real-company store performance

## Benchmark catalog

File: `data/retailer_simulation/public_benchmarks.yaml`

Each benchmark carries a `verification_state`:

| State | Effect |
| --- | --- |
| `VERIFIED` | Active anchor used in generation |
| `DEMO_DEFAULT` | Active demo anchor; labeled as default |
| `UNVERIFIED_DISABLED` | Catalogued only; **never** affects generation |

## Running a simulation

### API (stateless)

```bash
curl -s http://localhost:8000/api/retailer-simulation/benchmarks | jq .
curl -s -X POST http://localhost:8000/api/retailer-simulation/run \
  -H 'Content-Type: application/json' \
  -d '{"store_count":48,"seed":42,"sales_target_usd":200000000}' | jq .
```

### API (session-scoped)

```bash
SESSION=$(curl -s -X POST http://localhost:8000/api/sessions | jq -r .session_id)
curl -s -X POST "http://localhost:8000/api/sessions/$SESSION/retailer-simulation/run" \
  -H 'Content-Type: application/json' \
  -d '{"store_count":24,"seed":7,"sales_target_usd":120000000}' | jq .
curl -s "http://localhost:8000/api/sessions/$SESSION/retailer-simulation" | jq .
```

### UI

1. Complete the governed workflow through **Approve** so the workspace reaches the executed stage.
2. Open the **Retailer simulation** tab in the intelligence panel.
3. Review the **Simulated retailer data** banner and public benchmark sources.
4. Adjust explicit scenario inputs (store count, seed, sales target, format mix, margin range).
5. Click **Run simulation**. Results include store list, monthly distribution, segments, seed/version, and reconciliation pass/fail.

## Reconciliation

After generation, a reconciliation report compares targets vs outputs:

- Total annual sales vs explicit `sales_target_usd` (1% tolerance)
- Monthly roll-up vs annual total
- Store count referential integrity
- Segment shares sum to 100%
- Margins within scenario range
- No negative values

## Determinism

Same `seed` + same scenario parameters ⇒ identical artifact. Different seed ⇒ different
valid outputs. Simulator version: `northstar_v1`.

## Capability

Registered as `retailer.scenario_simulation` (available) in `planning/capabilities.py`.
