# From prototype to a governed retail site-selection platform

## What this prototype already establishes

Five things transfer directly, and they are the expensive ones to retrofit:

1. **A separation of powers that survives scale.** The agent plans and explains;
   deterministic services decide what is true. Adding data sources, metrics, or users does
   not widen the model's authority, because that authority is bounded by an allowlist and
   a registry rather than by a prompt.
2. **Provenance as a data structure, not a convention.** Every value is an object carrying
   its datapoint id, geography, period, source, validation status, and originating API
   call. Audit, lineage, and regulatory explainability are then reporting problems rather
   than re-architecture problems.
3. **Refusal as a first-class outcome.** The system already distinguishes "I can answer
   this", "I can answer part of this", and "this is not answerable from evidence". That
   distinction is what makes an analytical tool safe to put in front of an executive.
4. **An approval gate with a versioned plan behind it.** `AnalysisPlanProposal` is already
   the unit of authorization: it is versioned, carries an approval record and a human-edit
   log, and is the only thing the pipeline will execute. Enterprise workflow — multi-party
   sign-off, delegated approval, retention — is then a matter of who may set the approval
   record, not a change to how execution is gated.
5. **A capability registry that names its own gaps.** Every future data source in this
   document already exists in the system as a declared unavailable capability with its
   required inputs and expected provider. Adding one is a registry entry plus an adapter,
   not a planner rewrite.

## Adding a governed tool

The registry is designed so that the planner does not change when the toolset does. A new
capability is four things:

1. **A `Capability` entry** moving from `_UNAVAILABLE` to `_AVAILABLE`, with what it
   consumes and what it produces.
2. **A provider adapter** behind the same interface as the Atlas client: bounded retries,
   timeouts, credential redaction, and a `RawCall` record for every request.
3. **Validation rules** for the new comparability questions the source introduces. This is
   the hard part, and it is discussed below.
4. **Registry metrics**, each verified against the live provider before it can be selected,
   exactly as Atlas datapoints are today.

What does *not* change: the planner still emits metric ids from an allowlist, the scorer
still owns the arithmetic, and the plan still requires approval. That invariance is the
whole reason to build the registry before the tools.

### The capabilities currently declared unavailable

Each of these is in `planning/capabilities.py` today with its required data and expected
provider, and each is something the agent may recommend as a next step and can never
simulate.

| Capability | What it would need | Provider type | Hard part |
| --- | --- | --- | --- |
| **Retailer transaction data** | Basket, loyalty, and store-level sales history | The retailer's own warehouse | Governance, not integration. This is the most sensitive data in the system and the one that turns a describing tool into a predicting one |
| **Existing store network** | Store locations, formats, opening dates, performance | Retailer master data | Reconciling a store list against trade areas that overlap and change |
| **Competitor locations** | Competitor sites, banners, formats, approximate size | Commercial competitive-intelligence feed | Coverage is uneven and staleness is invisible; needs an explicit freshness field surfaced like a period is today |
| **Foot traffic** | Observed pedestrian or vehicle counts at candidate sites | Mobility data provider | Panel-based counts are modelled estimates, not observations. They must carry uncertainty into the score or they will be over-trusted |
| **Lease and construction cost** | Asking rent, CAM, escalators, term, build-out estimates | Commercial real-estate data plus internal construction estimates | Comparability across markets and lease structures; a headline rent is not a cost |
| **Drive-time trade areas** | Isochrone generation around candidate sites | Atlas already supports this on a commercial license | Cheapest and highest-value of the set. Changes what "the market" means, and every existing metric works unchanged against the new polygon |
| **Cannibalization modelling** | Existing network plus overlapping trade areas plus transaction data | Composite of the above | Depends on three other capabilities; genuinely a model rather than a retrieval, so it needs the outcome calibration described below |
| **Store-performance forecasting** | All of the above plus margin, supply-chain cost, and an approved methodology | Composite | The thing the system refuses today. It becomes answerable only with an approved, validated methodology — and should stay refused until then |

The sequencing implied by that table is deliberate: trade areas first because they cost the
least and change the most, then the external feeds, then the retailer's own data, then
anything that claims to predict.

## What has to change

### Data foundation

The demo token's three-county footprint is the binding constraint. A commercial StateBook
license unlocks national geography, and the same architecture then needs a **trade-area
model** rather than administrative boundaries. Atlas already supports radius, drive-time
isochrone, drive-distance, GeoJSON, and combined geographies; the client would use
drive-time catchments around candidate sites, which is how retail site selection is
actually done. That single change makes the comparison materially more credible than
comparing city polygons.

Atlas alone is insufficient, and the limitations panel already says so. Production
requires joining it to: **site inventory and lease economics** (rent, CAM, build-out,
term), **mobility data** for observed foot traffic, **competitive intelligence** for
competitor locations and formats, and the retailer's **own transaction, loyalty, and
existing-store performance data**. The registry pattern extends to these directly — each
source becomes a provider behind the same verified-metric interface, with the validation
layer arbitrating comparability across providers, which is a harder problem than
comparability within one.

### From a scoring heuristic to a defensible model

The weighted linear score is a communication device. It is transparent and reproducible,
but it makes no claim to predict performance. The production path is:

- **Propagate uncertainty.** Atlas publishes margins of error (`.moe`) and the model
  already captures them. Turning scores into intervals and suppressing rankings whose
  intervals overlap is the highest-value single improvement, and it generalises the
  near-tie gate that already exists.
- **Calibrate against outcomes.** With enough store-year observations, the weights stop
  being an executive's stated priority and become fitted coefficients on realised
  performance, with the priors retained as a regularisation prior and an explainability
  story.
- **Keep the deterministic core.** Whatever the model becomes, it stays a service the
  agent calls rather than arithmetic the agent performs. That property is what makes the
  output auditable, and it should not be traded away for convenience.

### Engineering and operations

| Area | Prototype | Production |
| --- | --- | --- |
| Runtime | FastAPI plus a Next.js client, both single-instance | The same two services, horizontally scaled; the pipeline is already a pure function over a request, so the only thing blocking replicas is the in-memory session store |
| Persistence | In-memory, JSON artifacts | Analysis runs, evidence packages, and raw calls stored immutably and addressed by the reproducibility hash |
| Caching | None | Response cache keyed by datapoint, geography, and period; Atlas billing is per call, so this is a cost control as much as a latency one |
| Metric registry | Python constants gated by a verification file | Versioned registry with review workflow, effective dates, and re-verification in CI against the live API |
| Identity | None | SSO, per-tenant data entitlements mirroring the license scope the allowlist already models |
| Observability | Structured JSON logs | Traces per analysis run, plus alerting on refusal-rate and validation-exclusion-rate drift, which are the leading indicators of upstream data change |
| Plan storage | In-memory server-side sessions, LRU-capped, lost on restart | Plans, versions, approvals, and revisions persisted as an immutable lineage, addressed by plan id and version, in shared storage behind an authenticated identity |
| Approval | Single user, in-session | Role-based approval, delegation, and an exportable authorization record per executed analysis |
| Testing | 315 offline Python, 29 frontend, 6 live | The live suite becomes a scheduled contract test; a golden-output suite pins scoring behaviour across releases; the generated frontend fixtures become a CI drift check rather than a manual regeneration |

### Governance

This is where the architecture pays off, and where an enterprise buyer will focus:

- **Model risk management.** The deterministic scorer is documentable and independently
  reproducible from the stored evidence package. The LLM sits outside the calculation
  path, which keeps it out of scope for most model-validation regimes.
- **Adversarial evaluation.** The pattern-based injection classifier is a prototype
  control and should be replaced with a dedicated classifier plus a red-team suite run in
  CI. The deterministic guarantees beneath it — allowlists, registry gating, output
  verification — are what bound the damage when detection misses, and they should be
  treated as the real boundary.
- **Data licensing.** Atlas restates its license on every response. Production needs
  per-tenant entitlement enforcement, redistribution controls on exports, and attribution
  carried through to any downstream artifact.
- **Human-in-the-loop.** Already load-bearing rather than advisory: no analysis executes
  without an approval record, and no revision applies without a confirmation. Production
  extends this to role-based approval and makes acknowledgement of the limitations panel a
  gate on export into an investment memo.
- **Agent authority as a reviewable artifact.** The decision log already labels every step
  with what authorized it. An enterprise deployment should be able to produce, per
  analysis, the set of decisions the model influenced and the validation outcome for each —
  which is a query over existing data rather than new instrumentation.

## Sequencing

| Phase | Focus | Outcome |
| --- | --- | --- |
| 1 | Commercial license, drive-time trade areas, response caching, persisted plans and runs | Credible national comparisons on real catchments, with an auditable plan lineage |
| 2 | Uncertainty propagation, site and lease data, competitive locations | Recommendations that survive a real-estate committee |
| 3 | Retailer transaction data, outcome calibration, cannibalization modelling | A model that predicts rather than describes |
| 4 | Multi-tenant governance, role-based approval, audit, model-risk documentation | Sellable into an enterprise procurement process |

The through-line is that phases 2 through 4 add data, rigour, and controls without
revisiting the trust architecture. That is the point of building it first.

Everything in this document describes future architecture. What is implemented today is
the Atlas-only comparison, the planning and approval workflow around it, and the declared
gaps — nothing in the capability table above executes.
