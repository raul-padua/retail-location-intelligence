# From prototype to a governed retail site-selection platform

## What this prototype already establishes

Three things transfer directly, and they are the expensive ones to retrofit:

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
| Runtime | Streamlit, single process | API service plus a separate web client; the pipeline is already a pure function over a request |
| Persistence | In-memory, JSON artifacts | Analysis runs, evidence packages, and raw calls stored immutably and addressed by the reproducibility hash |
| Caching | None | Response cache keyed by datapoint, geography, and period; Atlas billing is per call, so this is a cost control as much as a latency one |
| Metric registry | Python constants gated by a verification file | Versioned registry with review workflow, effective dates, and re-verification in CI against the live API |
| Identity | None | SSO, per-tenant data entitlements mirroring the license scope the allowlist already models |
| Observability | Structured JSON logs | Traces per analysis run, plus alerting on refusal-rate and validation-exclusion-rate drift, which are the leading indicators of upstream data change |
| Testing | 103 offline, 6 live | The live suite becomes a scheduled contract test; a golden-output suite pins scoring behaviour across releases |

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
- **Human-in-the-loop.** A site-selection recommendation should require analyst
  acknowledgement of the limitations panel before it can be exported into an investment
  memo. The panel already exists; production makes acknowledging it a gate.

## Sequencing

| Phase | Focus | Outcome |
| --- | --- | --- |
| 1 | Commercial license, drive-time trade areas, response caching, persisted runs | Credible national comparisons on real catchments |
| 2 | Uncertainty propagation, site and lease data, competitive locations | Recommendations that survive a real-estate committee |
| 3 | Retailer transaction data, outcome calibration, cannibalization modelling | A model that predicts rather than describes |
| 4 | Multi-tenant governance, audit, model-risk documentation | Sellable into an enterprise procurement process |

The through-line is that phases 2 through 4 add data, rigour, and controls without
revisiting the trust architecture. That is the point of building it first.
