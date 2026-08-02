# Sample output: the planning and revision arc

Produced by driving `app/workflow.py` end to end with no language model configured, so everything below came from the deterministic planner.

**Objective as written**  
> We are evaluating Burlington, South Burlington, and Winooski for a suburban apparel store targeting middle-income families. Prioritize growth and accessibility over current market size.

## 1. What the planner inferred

Planner: Deterministic planner (no language model involved)

Compare 3 candidate region(s) on 13 verified Atlas metric(s), scoring each against five retail categories. The objective emphasised Accessibility, Growth Outlook, so those categories carry more weight. It ranked Market Potential below those, so they carry less. This plan was generated deterministically by pattern matching, with no language model involved.

| Profile field | Value | Provenance |
| --- | --- | --- |
| retailer type | Mainstream apparel retailer | planner_inferred |
| store format | suburban | planner_inferred |
| target customer segments | middle-income families | user_supplied |
| strategic priorities | Accessibility, Growth Outlook | user_supplied |
| secondary priorities | Market Potential | user_supplied |
| hard constraints | _not established_ | unknown |
| preferred market type | suburban | planner_inferred |
| trade area definition | _not established_ | unknown |
| risk tolerance | _not established_ | unknown |
| requested dimensions | _not established_ | unknown |

### Proposed category weights

| Category | Weight |
| --- | --- |
| Market Potential | 13.6% |
| Customer Fit | 22.7% |
| Economic Attractiveness | 18.2% |
| Accessibility | 18.2% |
| Growth Outlook | 27.3% |

### Assumptions, with their basis

- **retailer_type**: Mainstream apparel retailer (No retailer type was stated. The prototype's illustrative scenario is a national mainstream apparel banner; this only affects the wording of the narrative, not the metrics or the score.)
- **store_format**: suburban (The objective described the store as 'suburban'.)
- **preferred_market_type**: suburban (Read from the objective's description of a suburban store.)
- **Trade-area definition**: Treat each named municipality or county as the market. (You have not answered: "Should each municipality be treated as the market, or would you ultimately use drive-time trade areas?" The analysis proceeds on this default and discloses it.)
- **Category weighting**: Accessibility was raised because the objective named it as a priority ("accessibility"). (Priority phrases raise a category by 2x and explicitly deprioritised ones by 0.5x, before renormalizing to sum to 1.)
- **Category weighting**: Growth Outlook was raised because the objective named it as a priority ("growth"). (Priority phrases raise a category by 2x and explicitly deprioritised ones by 0.5x, before renormalizing to sum to 1.)
- **Category weighting**: Market Potential was lowered because the objective ranked it below the priorities ("market size"). (Priority phrases raise a category by 2x and explicitly deprioritised ones by 0.5x, before renormalizing to sum to 1.)

### Clarifications asked

- _Should each municipality be treated as the market, or would you ultimately use drive-time trade areas?_ (optional) - Administrative boundaries rarely match a real catchment. Knowing you intend drive-time areas does not change what I can compute, but it changes how much weight the result should carry.

## 2. Deterministic validation

Status: `passed`

| Check | Passed | Detail |
| --- | --- | --- |
| candidate_geographies | yes | 3 distinct region(s) resolved against the licensed allowlist: city:burlington-vt, city:south-burlington-vt, city:winooski-vt. |
| selected_metrics | yes | All 13 selected metric(s) exist in the verified registry. |
| metric_geography_support | yes | 13 of 13 selected metric(s) are published at every candidate's geographic level. |
| category_weights | yes | All category weights are finite, non-negative, and normalized to sum to 1. |
| metric_weight_overrides | yes | No per-metric weight overrides were requested. |
| required_clarifications | yes | No required question is outstanding. 1 optional question(s) will proceed on a disclosed default. |
| unsupported_disclosed | yes | 0 unsupported requirement(s) are disclosed with a reason and a data source that would satisfy them. |
| assumptions_visible | yes | 7 plan assumption(s) and 3 inferred profile field(s) are shown with their basis. |

## 3. Approved, executed, then revised

Version 1 ran on approval and produced hash `f70ef2ec7455c4b8`, leader **South Burlington, VT**.

The request _"Double the importance of household income"_ produced a revision proposal, which was confirmed and created version 2.

### Weight changes

| Category | Before | After |
| --- | --- | --- |
| Market Potential | 13.6% | 11.5% |
| Customer Fit | 22.7% | 19.2% |
| Economic Attractiveness | 18.2% | 30.8% |
| Accessibility | 18.2% | 15.4% |
| Growth Outlook | 27.3% | 23.1% |

### Result delta

| Region | Rank before | Rank after | Score before | Score after |
| --- | --- | --- | --- | --- |
| South Burlington, VT | 1 | 1 | 54.14 | 56.45 |
| Winooski, VT | 3 | 2 | 41.19 | 42.65 |
| Burlington, VT | 2 | 3 | 43.81 | 37.07 |

New hash `f3f2b8f2d09e0661`, leader **South Burlington, VT**. The leader held.

### Attribution

- Market Potential moved from 14% to 12%.
- Customer Fit moved from 23% to 19%.
- Economic Attractiveness moved from 18% to 31%.
- Accessibility moved from 18% to 15%.
- Growth Outlook moved from 27% to 23%.
- Winooski, VT moved up 1 place(s), from rank 3 to rank 2.
- Burlington, VT moved down 1 place(s), from rank 2 to rank 3.
- The reproducibility hash changed from f70ef2ec7455c4b8 to f3f2b8f2d09e0661, which confirms the inputs to the calculation are genuinely different rather than the same run relabelled.
- The evidence is identical in both versions: the same Atlas values, periods, and sources. Only the weighting differs, so this is a change of emphasis rather than a change of fact.

## 4. Who authorized what

| # | Step | Authority |
| --- | --- | --- |
| 1 | objective_received | User supplied |
| 2 | classify_objective | Deterministic validation |
| 3 | planner_output | Agent inference |
| 4 | validate_plan | Deterministic validation |
| 5 | revision_confirmed | Human approval |
| 6 | plan_approved | Human approval |
| 7 | parse_intent | Deterministic validation |
| 8 | resolve_geographies | Deterministic validation |
| 9 | select_metrics | Agent inference |
| 10 | atlas_calls | API evidence |
| 11 | validate_evidence | Deterministic validation |
| 12 | deterministic_scoring | Deterministic calculation |
| 13 | explanation | Explanation layer |
