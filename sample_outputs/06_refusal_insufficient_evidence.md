# Sample output: 06_refusal_insufficient_evidence

**Question**: Rank these on population and income only.

**Candidate regions**: city:burlington-vt, city:south-burlington-vt

**Outcome**: REFUSED

**Reproducibility hash**: `f819ed8201759039`

## Refusal

The available evidence does not support ranking these regions reliably. Only 2 metric(s) survived validation, below the 3 required for a stable ranking. A score built on so few indicators would swing on any one of them.

### Why it is unsupportable

- Only 2 metric(s) survived validation, below the 3 required for a stable ranking. A score built on so few indicators would swing on any one of them.
- 0 metric(s) were excluded by validation, so the score rests on a narrower base than the model intends.

### What would be required

- Additional Atlas metrics that are published at every candidate region's geographic level.
- A commercial StateBook license covering a wider set of candidate regions.
- Retailer-supplied inputs such as site costs, foot traffic, and competitor presence to break a statistical tie on business grounds.

### Offered instead

The per-metric comparison and full evidence table are still shown below, with every value traceable to its Atlas response. They can be reviewed directly, but they should not be collapsed into a single ranking.

## Evidence

Package `pkg_646356f07e` from 1 Atlas call(s).

| Metric | Atlas datapoint | Region | Raw value | Period | Source | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Median Household Income | `dem.acs.hhd.mdinc.val` | city:burlington-vt | 7.111e+04 | 2024 | acs5 | valid |
| Median Household Income | `dem.acs.hhd.mdinc.val` | city:south-burlington-vt | 1.067e+05 | 2024 | acs5 | valid |
| Total Population | `dem.acs.pop.total.val` | city:burlington-vt | 4.468e+04 | 2024 | acs5 | valid |
| Total Population | `dem.acs.pop.total.val` | city:south-burlington-vt | 2.076e+04 | 2024 | acs5 | valid |

## Execution trace

1. **parse_intent** - Question sanitized and classified before any tool selection.
2. **resolve_geographies** - Resolved 2 candidate region(s) against the token's allowlist; rejected 0.
3. **select_metrics** - Selected 2 approved metric(s); excluded 0 before any API call.
4. **atlas_calls** - Issued 1 Atlas request(s).
5. **validate_evidence** - 2 metric(s) passed every comparability gate; 0 were rejected during validation.
6. **deterministic_scoring** - Normalized and weighted 2 metric(s). Reproducibility hash f819ed8201759039.
7. **sufficiency_gate** - Ranking withheld: evidence is insufficient to separate the candidates.

## Limitations

- **[caution] Demo token geographic restriction**: The public demo token only licenses the Burlington-South Burlington, VT metro area (Chittenden, Franklin, and Grand Isle counties and the cities within them). Regions outside that footprint require a commercial StateBook license.
- **[caution] Market indicators are not a site-selection decision**: Atlas describes geographic areas. A real store investment additionally requires site-level rent and build-out cost, observed foot traffic, competitor locations and formats, cannibalization of the existing store network, category margin, supply-chain cost to serve, and the retailer's own transaction data. None of that is available here.
- **[caution] Two-region comparison produces extreme normalized scores**: Min-max normalization places the better region at 100 and the other at 0 on every metric, regardless of whether the gap between them is large or trivial. The ordering is meaningful; the size of the gap is not. Add a third region, or read the raw values in the evidence panel, to judge magnitude.
- **[info] Survey estimates carry sampling error**: American Community Survey values are 5-year rolling estimates with margins of error that widen for smaller places. Small differences between similarly sized regions may not be statistically meaningful.
- **[blocking] Ranking withheld**: Only 2 metric(s) survived validation, below the 3 required for a stable ranking. A score built on so few indicators would swing on any one of them.
