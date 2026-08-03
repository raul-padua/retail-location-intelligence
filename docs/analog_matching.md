# Analog store matching (Phase 4)

Rank **NorthStar Apparel** simulated stores against a candidate market using **public ACS
county features only**. Matching math runs in Python; the UI renders projections.

## Plain-language purpose

Site selectors often ask: *“Where have we already seen markets like this one?”* Analog
search finds the closest cousins among the fictional NorthStar stores by comparing public
market characteristics (income, age mix, density, and so on). Only after those look-alikes
are ranked does the UI show their **simulated** sales — as demo context for “markets like
this,” not as a forecast for the candidate site.

**Retailer simulation** builds the fictional network and can profile stores in the same
public-market archetype as the selected area. **Analog stores** ranks specific look-alike
stores and explains *why* they match feature by feature.

## What this answers

- Which synthetic stores sit in host counties that resemble the candidate market profile?
- Which public-market features drive similarity (per-feature contributions)?
- What might simulated performance look like for ranked analogs — **after** ranking, always
  labeled `SIMULATED_RETAILER_DATA`?

## What this does not answer

- Observed GAP or any real retailer store performance
- Forecasted sales for a new site (see unavailable `future.financial_forecasting`)
- Trade-area or drive-time catchments

## Matching features

Only ids from `analog_matching/features.py` enter the distance vector — the same ACS-shaped
registry as market discovery (`PUBLIC_MARKET_DATA`):

| Feature id | Role |
| --- | --- |
| `population_total` | Market size |
| `population_density` | Urban vs dispersed |
| `median_household_income` | Spending power |
| `pct_bachelor_or_higher` | Education mix |
| `median_age` | Age structure |
| `pct_age_25_44` | Prime-age cohort |
| `pct_owner_occupied` / `pct_renter_occupied` | Tenure mix |
| `mean_commute_minutes` | Time-budget proxy |
| `labor_force_participation` | Daytime economy |

**Forbidden in the match vector:** `annual_sales_usd`, `gross_margin_pct`, and any
performance roll-ups (outcome leakage).

## Algorithm (deterministic)

1. Resolve candidate market → county GEOID (Atlas slug or 5-digit GEOID).
2. Build candidate z-scored feature vector from the market-discovery artifact.
3. Assign each simulated store a **host county** = nearest artifact county centroid (tie-break GEOID).
4. Weighted Euclidean distance on z-scored features + categorical penalties:
   - Optional `preferred_format` mismatch adds a fixed penalty.
   - Same archetype cluster as candidate applies a small bonus.
5. Similarity = `1 / (1 + distance)`; ties break on `store_id`.
6. Attach median/IQR sales and margin **only on ranked matches** for display.

Weak or insufficient analogs set `analogy_strength` and `warnings` when similarity or peer
count falls below configured thresholds.

## API

```bash
# Metadata
curl -s http://localhost:8000/api/analog-matching/meta | jq .

# Stateless search (runs or accepts scenario)
curl -s -X POST http://localhost:8000/api/analog-matching/search \
  -H 'Content-Type: application/json' \
  -d '{"market_id":"city:burlington-vt","top_k":5,"preferred_format":"mall"}' | jq .

# Session-scoped (persists last result)
curl -s -X POST http://localhost:8000/api/sessions/{id}/analog-matching/search \
  -H 'Content-Type: application/json' \
  -d '{"market_id":"county:chittenden-county-vt","top_k":5}' | jq .

curl -s http://localhost:8000/api/sessions/{id}/analog-matching | jq .
```

Reuses the session's last NorthStar simulation when seed/scenario match; otherwise generates
with explicit scenario defaults.

## UI

**Executed → Analog stores** tab:

1. Select a candidate on the map (shared selection with Archetypes).
2. Optionally set top-K and preferred format.
3. Click **Search analog stores**.
4. Review ranked cards, analogy strength, warnings, and contribution chart for a selected match.
5. Simulated performance always shows the `SIMULATED_RETAILER_DATA` badge.

## Capability

`retailer.analog_store_search` — available, deterministic.

## Assistant

The search payload includes a `context_pack` (factual strings only). When a session has a
last analog search, the assistant context includes those lines — no invented numbers.

## Related docs

- `docs/market_discovery.md` — candidate market profiles
- `docs/synthetic_retailer.md` — NorthStar simulation
- `docs/data_provenance.md` — data-class labeling
