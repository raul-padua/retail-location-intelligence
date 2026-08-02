# Metric registry

Every metric below names a StateBook Atlas datapoint that was confirmed to return a value from the live API. The registry refuses to load if any entry is missing from `data/atlas_verified_datapoints.json`, so a datapoint identifier that was never observed cannot enter the scoring model.

Generated 2026-08-01 by `scripts/generate_metric_doc.py`.

## How this list was produced

The Atlas documentation states that the published datapoint list is "[URL to be determined]", so the catalogue was discovered rather than read:

1. `scripts/crawl_atlas_catalog.py` walks the public Calypso topic configuration at `https://api.statebook.com/api/v1/config/`, where a *category* is a datapoint prefix and *metrics* are the suffixes that may be appended to it (`val`, `ayc`, `aycp`, `moe`, `pct`). That produced 1,759 candidate identifiers.
2. `scripts/verify_datapoints.py` calls the live API for every candidate across a metro, a county, and two cities of very different size, and records which identifiers actually return a value. 662 were confirmed.
3. The metrics below were selected from the confirmed set on retail relevance. Atlas rejects an unknown identifier outright with `Unknown datapoint specified`, which is the final backstop against a fabricated id.

## Units

Atlas returns American Community Survey shares as proportions (`0.9517` for 95.17%), not in the 0-100 form the documentation describes. The registry records the proportion form and the interface multiplies for display. No conversion happens before scoring, so normalization operates on the values Atlas returned.

## Category weights

Default weights, adjustable in the interface before recalculating:

| Category | Default weight |
| --- | --- |
| Market Potential | 30% |
| Customer Fit | 25% |
| Economic Attractiveness | 20% |
| Accessibility | 10% |
| Growth Outlook | 15% |

Within a category, metric weights are relative and are renormalized to sum to 1 over whichever metrics survived validation for a given region. Across categories, weights are renormalized over whichever categories produced a score. Both adjustments are disclosed in the trace panel.

## Metrics

### Market Potential (default weight 30%)

#### Civilian Labor Force

- **Atlas identifier**: `wkf.acs.emp.16pl.labor.civ.total.val`
- **Verified description**: Civilian Labor Force
- **Attribution**: US Census, ACS
- **Unit**: people
- **Direction**: higher is better
- **Weight within category**: 0.25
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: The working population is a proxy for daytime presence and for workwear and commuter-driven apparel demand, which resident counts alone understate.

#### Retail Trade Establishments (NAICS 44)

- **Atlas identifier**: `ind.cbp.naics.est.val (collection `ind.cbp.naics`, item `44`)`
- **Verified description**: Establishments
- **Attribution**: US Census, CBP
- **Unit**: establishments
- **Direction**: higher is better
- **Weight within category**: 0.3
- **Normalization**: min_max
- **Observed period**: 2023
- **Observed source**: n/a
- **Published at**: cbsa, county
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: The density of existing retail establishments proxies for established shopping activity and co-tenancy: apparel performs better beside other retail, not in isolation.
- **Caveat**: County Business Patterns is not published below county level. Requesting it for a city causes Atlas to answer with the parent county, which the validation layer detects and excludes.

#### Total Households

- **Atlas identifier**: `dem.acs.hhd.total.val`
- **Verified description**: Total Households
- **Attribution**: US Census, ACS
- **Unit**: households
- **Direction**: higher is better
- **Weight within category**: 0.35
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Apparel purchasing is substantially a household decision, particularly for children's and family lines, so household count often tracks demand better than headcount alone.

#### Total Population

- **Atlas identifier**: `dem.acs.pop.total.val`
- **Verified description**: Population
- **Attribution**: US Census, ACS
- **Unit**: people
- **Direction**: higher is better
- **Weight within category**: 0.4
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: The size of the resident population bounds the addressable customer base for a physical store. It is the coarsest but most reliable proxy for trade-area demand.

### Customer Fit (default weight 25%)

#### Bachelor's Degree or Higher (25+)

- **Atlas identifier**: `edu.acs.att.25pl.bachpl.pct`
- **Verified description**: Bachelor Degree or Higher Attainment (25+) %
- **Attribution**: US Census, ACS
- **Unit**: percent
- **Direction**: higher is better
- **Weight within category**: 0.35
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Educational attainment correlates with discretionary spending capacity and with brand-oriented apparel purchasing, independent of headline income.

#### Median Age

- **Atlas identifier**: `dem.acs.mdage.total.val`
- **Verified description**: Median Age
- **Attribution**: US Census, ACS
- **Unit**: years
- **Direction**: lower is better
- **Weight within category**: 0.3
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: A mainstream apparel banner skews toward younger adult and family shoppers, so a lower median age is treated as a better fit for this retailer profile.
- **Caveat**: Direction is a profile assumption, not a property of the data. A retailer targeting older shoppers should invert it.

#### College / Undergraduate Enrollment Share (3+)

- **Atlas identifier**: `edu.acs.enr.3pl.ugrad.pct`
- **Verified description**: College / Undergrad Enrollments (3+) %
- **Attribution**: US Census, ACS
- **Unit**: percent
- **Direction**: higher is better
- **Weight within category**: 0.35
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: A large student population signals a concentrated, footfall-heavy, fashion-responsive segment near campus retail corridors.

### Economic Attractiveness (default weight 20%)

#### Employed Share of Civilian Labor Force

- **Atlas identifier**: `wkf.acs.emp.16pl.labor.civ.emp.pct`
- **Verified description**: Employed Civilian Labor Force %
- **Attribution**: US Census, ACS
- **Unit**: percent
- **Direction**: higher is better
- **Weight within category**: 0.35
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Employment stability underpins sustained discretionary spend. Apparel is among the first categories cut when local employment weakens.

#### Median Household Income

- **Atlas identifier**: `dem.acs.hhd.mdinc.val`
- **Verified description**: Household Median Income
- **Attribution**: US Census, ACS
- **Unit**: usd
- **Direction**: higher is better
- **Weight within category**: 0.4
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: The most direct available proxy for purchasing power in the trade area. Median is preferred to mean because it is less distorted by a small number of very high earners.

#### Per Capita Income

- **Atlas identifier**: `dem.acs.hhd.pcinc.val`
- **Verified description**: Per Capita Income
- **Attribution**: US Census, ACS
- **Unit**: usd
- **Direction**: higher is better
- **Weight within category**: 0.25
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Complements household income by adjusting for household size, which matters where student or single-person households are concentrated.

### Accessibility (default weight 10%)

#### Food Service & Drinking Establishments (NAICS 722)

- **Atlas identifier**: `ind.cbp.naics.est.val (collection `ind.cbp.naics`, item `722`)`
- **Verified description**: Establishments
- **Attribution**: US Census, CBP
- **Unit**: establishments
- **Direction**: higher is better
- **Weight within category**: 1.0
- **Normalization**: min_max
- **Observed period**: 2023
- **Observed source**: n/a
- **Published at**: cbsa, county
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Restaurants and bars are a widely used proxy for destination footfall and dwell time, which apparel retail depends on.
- **Caveat**: County level and above only, for the same reason as retail establishments.

#### Mean Commute Travel Time

- **Atlas identifier**: `trn.acs.cmt.mean.val`
- **Verified description**: Commuters Mean Travel Time
- **Attribution**: US Census, ACS
- **Unit**: minutes
- **Direction**: lower is better
- **Weight within category**: 1.0
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Shorter commutes indicate a more compact, accessible catchment where shoppers can reach a store without a long trip. Reported in minutes.
- **Caveat**: This is the only accessibility indicator the demo token exposes at every geographic level; it is a weak proxy for true trade-area accessibility.

### Growth Outlook (default weight 15%)

#### Household Average Yearly Change

- **Atlas identifier**: `dem.acs.hhd.total.aycp`
- **Verified description**: Total Households AYC %
- **Attribution**: US Census, ACS
- **Unit**: percent
- **Direction**: higher is better
- **Weight within category**: 0.3
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Household formation drives new demand for apparel and home-adjacent categories more directly than raw population change.

#### Household Median Income Average Yearly Change

- **Atlas identifier**: `dem.acs.hhd.mdinc.aycp`
- **Verified description**: Household Median Income AYC %
- **Attribution**: US Census, ACS
- **Unit**: percent
- **Direction**: higher is better
- **Weight within category**: 0.3
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: Rising local incomes expand discretionary budgets. Nominal, so it is not inflation-adjusted and should not be read as real purchasing-power growth.
- **Caveat**: Nominal growth. Not adjusted for inflation.

#### Population Average Yearly Change

- **Atlas identifier**: `dem.acs.pop.total.aycp`
- **Verified description**: Population AYC %
- **Attribution**: US Census, ACS
- **Unit**: percent
- **Direction**: higher is better
- **Weight within category**: 0.4
- **Normalization**: min_max
- **Observed period**: 2024
- **Observed source**: acs5
- **Published at**: cbsa, county, city
- **Verified in**: 4 of the probed geographies
- **Why it matters to a retailer**: A store is a multi-year commitment, so the direction of the trade area matters as much as its current size.

## Dimensions that are deliberately absent

The brief asks for several retail-location dimensions. These were investigated and excluded because Atlas does not support them at the required resolution, or at all:

| Dimension | Status |
| --- | --- |
| Population density / land area | No scalar density or land-area datapoint was confirmed in the verified set, so density could not be derived from Atlas values alone. Total population is used as the market-size proxy instead. |
| Transportation accessibility (airports, ports) | Available only as point-level collections (`trn.airport`, `trn.port`) that describe facility attributes rather than a comparable regional score. Mean commute time is used instead. |
| Commute mode share | `trn.acs.cmt.mode.wkf.*` is a collection keyed by travel mode. Supported by the client, but not yet reduced to a defensible single accessibility indicator. |
| Retail and food-service establishments | Included, but published only at county level and above. Requesting them for a city causes Atlas to answer with the parent county, which the validation layer detects and excludes. |
| Foot traffic, competitor locations, rent, transaction data | Not present in Atlas at any resolution. Requests that depend on them are refused. |

## Regenerating

```bash
uv run python scripts/crawl_atlas_catalog.py   # discover candidate identifiers
uv run python scripts/verify_datapoints.py     # confirm them against the live API
uv run python scripts/generate_metric_doc.py   # rewrite this document
```
