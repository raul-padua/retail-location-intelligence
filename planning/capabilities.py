"""The governed capability registry.

Every analytical operation the agent may request is enumerated here, and so is every
operation it may not. The planner receives this list and selects ids from it. It cannot
name a Python function, and a capability id it invents resolves to nothing.

The unavailable half is load-bearing. A site-selection conversation reaches rent,
competitors, and cannibalization almost immediately, and an agent with no representation
of those either improvises or stonewalls. Naming them, with the data each would require
and the reason this system cannot execute it, lets the agent recommend a real next step
while remaining structurally incapable of pretending one ran.

Adding a capability later is a data change here plus an executor entry in the pipeline.
The planner does not need to be rewritten, which is the point of routing everything
through ids.
"""

from __future__ import annotations

from functools import lru_cache

from models.capabilities import Capability, CapabilityKind, CapabilityStatus

_AVAILABLE: tuple[Capability, ...] = (
    Capability(
        capability_id="atlas.evidence_retrieval",
        display_name="StateBook Atlas evidence retrieval",
        kind=CapabilityKind.RETRIEVAL,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Fetch verified Atlas datapoints for the candidate regions, recording the "
            "request and response for every call."
        ),
        required_data=["Approved metric ids", "Licensed geography slugs"],
        produces="EvidenceItem objects carrying value, period, source, and datapoint id",
    ),
    Capability(
        capability_id="atlas.geography_resolution",
        display_name="Geography resolution",
        kind=CapabilityKind.RETRIEVAL,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Resolve free-text region names against the allowlist licensed by the active "
            "token. An unmatched name is refused rather than guessed."
        ),
        required_data=["Candidate region names"],
        produces="Geography objects, plus the list of inputs that were rejected",
    ),
    Capability(
        capability_id="validation.evidence_comparability",
        display_name="Evidence comparability validation",
        kind=CapabilityKind.VALIDATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Decide per metric whether the returned values may share an axis, checking "
            "schema, geographic resolution, period, source, unit, and coverage."
        ),
        required_data=["Fetched evidence"],
        produces="Surviving evidence plus an exclusion with a reason for each failure",
    ),
    Capability(
        capability_id="scoring.metric_normalization",
        display_name="Metric normalization",
        kind=CapabilityKind.CALCULATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Map raw values onto a 0-100 scale across the candidate set, by min-max or "
            "percentile rank, inverting where lower is better."
        ),
        required_data=["Validated evidence"],
        produces="A normalized score per region with the exact arithmetic recorded",
    ),
    Capability(
        capability_id="scoring.weighted_score",
        display_name="Weighted scoring and ranking",
        kind=CapabilityKind.CALCULATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Aggregate normalized metrics into category scores and an overall score using "
            "the approved weights, renormalizing and disclosing where data is missing."
        ),
        required_data=["Normalized evidence", "Category weights"],
        produces="A ranking with every intermediate value and a reproducibility hash",
    ),
    Capability(
        capability_id="scoring.evidence_sufficiency",
        display_name="Evidence sufficiency assessment",
        kind=CapabilityKind.VALIDATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Decide whether the surviving evidence can separate the candidates at all, "
            "and withhold the ranking when it cannot."
        ),
        required_data=["Scored regions", "Underlying raw values"],
        produces="A sufficiency decision with the reason it was reached",
    ),
    Capability(
        capability_id="scoring.strategy_profile_comparison",
        display_name="Strategy-profile comparison",
        kind=CapabilityKind.CALCULATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Re-score the same evidence under several documented weight profiles to show "
            "whether the ranking is a property of the market or of the weighting."
        ),
        required_data=["An executed evidence package"],
        produces="A ranking per profile, each with its own reproducibility hash",
    ),
    Capability(
        capability_id="scoring.weight_sensitivity",
        display_name="Weight sensitivity analysis",
        kind=CapabilityKind.CALCULATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Measure how far a category weight must move before the top two regions "
            "swap, and which metrics drive each region's score."
        ),
        required_data=["An executed evidence package"],
        produces="Deterministic stability findings; no estimation is involved",
    ),
    Capability(
        capability_id="explanation.evidence_bound",
        display_name="Evidence-bound explanation",
        kind=CapabilityKind.EXPLANATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Write an executive narrative from the validated evidence, with every figure "
            "verified against it before the text is accepted."
        ),
        required_data=["Evidence package", "Scoring output"],
        produces="A cited narrative, or the deterministic template if verification fails",
        deterministic=False,
    ),
    Capability(
        capability_id="retailer.scenario_simulation",
        display_name="Fictional retailer scenario simulation",
        kind=CapabilityKind.MODELLING,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Run a seeded, equation-based NorthStar Apparel simulator anchored to public "
            "aggregate benchmarks. Outputs are explicitly simulated — never observed "
            "retailer performance."
        ),
        required_data=[
            "Explicit scenario parameters (store count, format mix, seed, sales target)",
            "Public benchmark catalog with verification states",
        ],
        produces=(
            "Simulated stores, monthly roll-ups, segment shares, reconciliation report, "
            "and provenance metadata"
        ),
    ),
    Capability(
        capability_id="market.archetype_analysis",
        display_name="Market archetype analysis",
        kind=CapabilityKind.CALCULATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Look up a county's public-market archetype from a versioned, deterministic "
            "clustering artifact (ACS-shaped features; fixed seed; canonical cluster ids). "
            "Explains profile, peers, and quality caveats. Does not predict store sales."
        ),
        required_data=[
            "County GEOID or Atlas city/county slug mappable to a county",
            "Versioned market-discovery artifact",
        ],
        produces=(
            "Cluster id, deterministic label, feature profile vs centroid, nearest peer "
            "counties, and artifact quality metrics"
        ),
    ),
    Capability(
        capability_id="retailer.analog_store_search",
        display_name="Analog store matching",
        kind=CapabilityKind.CALCULATION,
        status=CapabilityStatus.AVAILABLE,
        description=(
            "Rank NorthStar Apparel simulated stores against a candidate market using "
            "public ACS county features only. Simulated sales and margins attach after "
            "ranking for display — they never enter the distance vector."
        ),
        required_data=[
            "County GEOID or Atlas slug for the candidate market",
            "NorthStar simulation (explicit scenario or session reuse)",
            "Versioned market-discovery county artifact",
        ],
        produces=(
            "Ranked analog matches with similarity, per-feature contributions, "
            "analogy-strength assessment, and simulated performance summaries"
        ),
    ),
)

_UNAVAILABLE: tuple[Capability, ...] = (
    Capability(
        capability_id="future.foot_traffic",
        display_name="Foot-traffic retrieval",
        kind=CapabilityKind.RETRIEVAL,
        status=CapabilityStatus.UNAVAILABLE,
        description="Observed pedestrian and vehicle counts at candidate sites.",
        required_data=[
            "Mobile-device or sensor-derived visit counts",
            "Site coordinates rather than administrative boundaries",
        ],
        expected_provider="A mobility data provider such as a device-panel vendor",
        unavailable_because=(
            "Atlas publishes statistics about geographic areas and carries no observed "
            "movement of people."
        ),
    ),
    Capability(
        capability_id="future.competitor_locations",
        display_name="Competitor-location analysis",
        kind=CapabilityKind.RETRIEVAL,
        status=CapabilityStatus.UNAVAILABLE,
        description="Where competing stores are, their formats, and their category share.",
        required_data=[
            "A competitor store directory with formats and footprints",
            "Category-level share estimates per trade area",
        ],
        expected_provider="A competitive-intelligence or point-of-interest data provider",
        unavailable_because="Atlas contains no information about individual businesses.",
    ),
    Capability(
        capability_id="future.cannibalization",
        display_name="Cannibalization modelling",
        kind=CapabilityKind.MODELLING,
        status=CapabilityStatus.UNAVAILABLE,
        description=(
            "Estimate how much of a new store's demand would be taken from the "
            "retailer's existing nearby stores."
        ),
        required_data=[
            "The retailer's existing store network with locations and formats",
            "Store-level historical sales",
            "Customer origin or trade-area overlap data",
            "A validated demand-transfer methodology",
        ],
        expected_provider="The retailer's own systems, plus a modelling methodology",
        unavailable_because=(
            "The system has no access to any retailer's store network or sales, and no "
            "approved transfer model to apply if it did."
        ),
    ),
    Capability(
        capability_id="future.transaction_analysis",
        display_name="Retailer transaction-data analysis",
        kind=CapabilityKind.RETRIEVAL,
        status=CapabilityStatus.UNAVAILABLE,
        description="Basket, loyalty, and customer-level purchasing behaviour.",
        required_data=[
            "Point-of-sale transaction history",
            "Loyalty or customer identity linkage",
        ],
        expected_provider="The retailer's own data warehouse, under a governed agreement",
        unavailable_because="No retailer data is connected to this prototype.",
    ),
    Capability(
        capability_id="future.real_estate_cost",
        display_name="Real-estate cost retrieval",
        kind=CapabilityKind.RETRIEVAL,
        status=CapabilityStatus.UNAVAILABLE,
        description="Asking rent, common-area charges, and build-out cost per site.",
        required_data=[
            "Commercial lease comparables for the candidate submarkets",
            "Construction and fit-out cost benchmarks",
        ],
        expected_provider="A commercial real-estate data provider or broker feed",
        unavailable_because="Atlas carries no property-market or construction-cost data.",
    ),
    Capability(
        capability_id="future.trade_area_generation",
        display_name="Drive-time trade-area generation",
        kind=CapabilityKind.CALCULATION,
        status=CapabilityStatus.UNAVAILABLE,
        description=(
            "Build catchments from drive-time isochrones rather than municipal "
            "boundaries, and aggregate demographics within them."
        ),
        required_data=[
            "A routing or isochrone service",
            "Demographics at a finer grain than the trade area, such as block group",
        ],
        expected_provider="A routing engine plus small-area census aggregation",
        unavailable_because=(
            "The current analysis uses administrative boundaries, which rarely match how "
            "a shopper actually reaches a store."
        ),
    ),
    Capability(
        capability_id="future.financial_forecasting",
        display_name="Store-performance and financial forecasting",
        kind=CapabilityKind.MODELLING,
        status=CapabilityStatus.UNAVAILABLE,
        description=(
            "Project sales, payback, or return on investment for a specific store at a "
            "specific site."
        ),
        required_data=[
            "Store format and merchandising plan",
            "Site rent, build-out cost, and operating cost",
            "Category gross margin and markdown assumptions",
            "Comparable-store performance to calibrate against",
            "A forecasting methodology approved by the retailer's finance function",
        ],
        expected_provider="The retailer's finance function, on top of all of the above",
        unavailable_because=(
            "Almost every input to such a model is absent, so any figure produced would "
            "be mostly assumption presented with the authority of a calculation."
        ),
    ),
)

# Maps the unsupported-dimension descriptions the intent layer already detects onto the
# capability that would one day satisfy them, so a refusal can point at a concrete path.
_REQUIREMENT_TO_CAPABILITY: dict[str, str] = {
    "pedestrian or vehicle counts at candidate sites": "future.foot_traffic",
    "competitor store locations and formats": "future.competitor_locations",
    "the retailer's own store network and overlapping trade areas": "future.cannibalization",
    "site-level lease and occupancy costs": "future.real_estate_cost",
    "build-out and construction cost estimates": "future.real_estate_cost",
    "category-level gross margin assumptions": "future.financial_forecasting",
    "distribution-network and freight cost modelling": "future.financial_forecasting",
    "the retailer's customer transaction and loyalty data": "future.transaction_analysis",
    "competitor revenue and category share data": "future.competitor_locations",
}


class CapabilityRegistry:
    """Lookup over the capability catalogue. Read-only by design."""

    def __init__(self, capabilities: tuple[Capability, ...]) -> None:
        self._by_id = {capability.capability_id: capability for capability in capabilities}

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, capability_id: object) -> bool:
        return capability_id in self._by_id

    def all(self) -> list[Capability]:
        return sorted(self._by_id.values(), key=lambda c: (c.status, c.capability_id))

    def get(self, capability_id: str) -> Capability | None:
        return self._by_id.get(capability_id)

    def available(self) -> list[Capability]:
        return [capability for capability in self.all() if capability.is_available]

    def unavailable(self) -> list[Capability]:
        return [capability for capability in self.all() if not capability.is_available]

    def available_ids(self) -> list[str]:
        return [capability.capability_id for capability in self.available()]

    def for_requirement(self, requirement: str) -> Capability | None:
        """The capability that would satisfy an unsupported dimension, if any."""
        capability_id = _REQUIREMENT_TO_CAPABILITY.get(requirement.strip().lower())
        return self.get(capability_id) if capability_id else None

    def describe_for_planner(self) -> str:
        """The capability section of the planner's machine-readable brief."""
        lines = ["AVAILABLE ANALYTICAL CAPABILITIES:"]
        lines += [f"- {c.describe_for_planner()}" for c in self.available()]
        lines.append("")
        lines.append(
            "UNAVAILABLE CAPABILITIES. These cannot run. You may recommend one as a next "
            "step, but you must never describe its output or imply it was executed:"
        )
        lines += [f"- {c.describe_for_planner()}" for c in self.unavailable()]
        return "\n".join(lines)


@lru_cache(maxsize=1)
def get_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry(_AVAILABLE + _UNAVAILABLE)
