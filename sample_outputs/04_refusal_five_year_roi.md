# Sample output: 04_refusal_five_year_roi

**Question**: Which city will generate the highest five-year ROI for GAP?

**Candidate regions**: city:burlington-vt, city:south-burlington-vt

**Outcome**: REFUSED

## Refusal

This asks for a company-specific financial projection. The StateBook Atlas API publishes observed market indicators for geographic areas; it contains no information about this retailer's economics, its stores, its customers, or its competitors. Producing a return-on-investment figure from these inputs would require inventing the majority of the model, and the resulting number would look authoritative while resting on assumptions the system cannot evidence.

### Why it is unsupportable

- Atlas describes areas, not businesses: it has no revenue, cost, or margin data.
- No store-level operating or site-cost inputs are available to the system.
- No approved forecasting methodology has been supplied or validated.
- Any multi-year projection would compound assumptions that cannot be traced to an API response.

### What would be required

- Store format, footprint, and merchandising plan for each candidate site.
- Site-level rent, common-area charges, and build-out or construction cost.
- Existing store network and modelled cannibalization of overlapping trade areas.
- Observed foot traffic or vehicle counts at the specific sites under consideration.
- Competitor locations, formats, and category share in each trade area.
- The retailer's own customer transaction, basket, and loyalty data.
- Category-level gross margin and markdown assumptions.
- Supply-chain and distribution cost to serve each location.
- Marketing and launch investment assumptions.
- A forecasting methodology approved by the retailer's finance function.

### Offered instead

The system can instead compare the candidate regions on the observable market indicators Atlas does publish - population and household base, income and purchasing-power proxies, age and education composition, employment, commute accessibility, and growth trends - and rank them with a transparent, reproducible score in which every value is traceable to an Atlas response. That output is an input to a return-on-investment model, not a substitute for one.

## Execution trace

1. **parse_intent** - Question refused: company_specific_forecast.

## Limitations

- **[caution] Demo token geographic restriction**: The public demo token only licenses the Burlington-South Burlington, VT metro area (Chittenden, Franklin, and Grand Isle counties and the cities within them). Regions outside that footprint require a commercial StateBook license.
- **[caution] Market indicators are not a site-selection decision**: Atlas describes geographic areas. A real store investment additionally requires site-level rent and build-out cost, observed foot traffic, competitor locations and formats, cannibalization of the existing store network, category margin, supply-chain cost to serve, and the retailer's own transaction data. None of that is available here.
