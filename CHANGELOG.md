# Change log

## 0.2.0 — Agentic planning, approval, and revision

The first version could answer a question. This one can work out what the question is.

The agent's authority moves from *selecting tools for a fixed analysis* to *constructing,
negotiating, revising, and orchestrating the analysis itself* — without gaining any
authority over evidence or calculation. Every deterministic guarantee from 0.1.0 is intact,
and several are now enforced at more points.

### Added

**Typed models for the decision, not just the analysis**

- `RetailStrategyProfile` (`models/strategy.py`), where every field is an `Attributed`
  value carrying one of four provenances: user-supplied, planner-inferred, unknown, or
  unsupported. "Unknown" is a first-class state, so nothing silently becomes an assumption.
- `AnalysisPlanProposal` (`models/plan.py`): versioned, frozen, auditable, with a status
  machine (`DRAFT`, `NEEDS_CLARIFICATION`, `READY_FOR_REVIEW`, `APPROVED`, `REJECTED`,
  `EXECUTED`, `SUPERSEDED`), an approval record, a human-edit log, and separate
  `can_approve` / `can_execute` gates.
- `PlanRevisionProposal`, `ClarificationQuestion`, `Assumption`, `UnsupportedRequirement`,
  `RejectedField`, `PlannerProvenance`, `PlanValidationReport`.
- `Capability` (`models/capabilities.py`) for the governed tool registry.
- `TraceAuthority` on every `TraceEntry`, with eight values distinguishing user input,
  agent inference, deterministic validation, API evidence, human approval, deterministic
  calculation, the explanation layer, and system bookkeeping.

**An agentic planner with a deterministic reference implementation**

- `planning/deterministic.py` maps priority phrases onto scoring categories, applies a
  documented boost/deprioritize rule with renormalization, infers a retailer profile with
  provenance, and generates materiality-based clarification questions — at most three per
  round, each recording the missing decision, why it matters, what it could change, whether
  it is required, and a safe default.
- `planning/llm_planner.py` gives a model a machine-readable capability brief and requires
  a strict typed schema back. Every field is revalidated: metric ids against the registry,
  geographies against the allowlist, weights against range and sum, and prose fields
  against detectors for Atlas datapoint patterns and factual figures. Validated
  contributions merge onto the deterministic baseline; any failure falls back to it
  entirely.
- `planning/planner.py` enforces the ordering that matters: classify untrusted text first,
  then plan, then validate. An injection or forecast request is refused before a planner
  exists.
- `planning/validation.py` — the deterministic gate that produces an approvable plan.
- `planning/capabilities.py` — nine available capabilities and seven declared unavailable
  ones (foot traffic, competitor locations, cannibalization, transaction data, real-estate
  cost, trade-area generation, forecasting), each with required data, expected provider,
  and why it cannot run today.

**Approval-gated execution**

- `AnalysisPipeline.run_approved()` is now the only path from a plan to an Atlas call. It
  consults `can_execute`, which requires validation passed, no unanswered required
  question, `APPROVED` status, *and* an approval record. A forged status is refused.
- The executed proposal is attached to the `AnalysisResult` for lineage.
- Confirming a revision authorizes the rerun, not its conclusion. A reweighted version
  whose top two regions fall inside the near-tie margin has its ranking withheld exactly as
  a first run would, and the prior version's answer survives untouched.
- Per-metric weight overrides, folded into the reproducibility hash.

**Sensitivity and comparison, all deterministic**

- Three documented strategy lenses — growth-focused, purchasing-power-focused,
  accessibility-focused — re-scoring the same evidence, each with its own reproducibility
  hash, plus a stability verdict.
- Metric influence decomposition: each metric's contribution in points of the 0–100 score.
- Flip-point scan: what one category weight would have to become to reverse the top two.
- `orchestration/comparison.py` diffs plan versions and results and attributes the change
  to the deterministic inputs that moved.

**A conversational analysis collaborator**

- The assistant classifies revision requests deterministically, behind the existing
  injection and forecast gates, and produces an inert `PlanRevisionProposal` with exact
  before/after values and a hedged statement of effect. Confirming creates version *n+1*;
  the previous version is marked superseded and its result retained.
- Unavailable-capability questions now name the capability, its required inputs, and the
  provider type that would supply it, rather than only refusing.
- The context pack includes the approved plan, so the assistant can explain *why this
  analysis* was run.

**A plan review and approval interface**

- `app/workflow.py`: the lifecycle as an explicit typed state machine with a fixed
  transition set and a `WorkflowError` for anything else. Execution is unreachable from the
  clarify stage. Guarantees live here rather than in Streamlit, which cannot enforce
  anything a browser rerun could bypass.
- Streamlit stages for describing the decision, clarifying, reviewing the proposal, editing
  and approving, and executing — plus new panels for sensitivity, version comparison, the
  approved plan, the capability registry, and an authority-filtered decision log.

### Changed

- The Streamlit entry point is now a natural-language objective rather than a sidebar form.
  Weights are still fully editable, but as an edit to a proposal that is revalidated and
  recorded, rather than as a direct input to a run.
- The trace is an agent decision log: every entry carries an authority, and the UI can
  filter on it.
- `detect_unsupported_dimensions` matches on word boundaries. It previously found "rent"
  inside "current" and told anyone asking about current population that the system had no
  lease-cost data.
- Prompt-injection patterns extended to cover approval bypass ("run it without approval",
  "auto-approve"), registry bypass ("ignore the registry"), and fabrication of specific
  business quantities.
- Priority reading is clause-scoped. When an objective states a priority explicitly, only
  the marked clause votes on the weights. "A suburban store for middle-income families,
  prioritize growth and accessibility" previously raised Customer Fit and Economic
  Attractiveness off a description of the *customer*, drowning out the two priorities the
  executive actually named. Demotion markers ("matters less", "less concerned about") are
  now read as well as promotion markers.
- Demo script rewritten for 7–8 minutes around the planning, approval, and revision arc.
- Architecture document extended with the planning and workflow layers, the end-to-end
  diagram, and the trace-as-accountability-record section.

### Tests

296 offline, 6 live. New suites:

| Suite | Covers |
| --- | --- |
| `test_plan_models.py` | Approval and execution gating, `Attributed` provenance |
| `test_planning.py` | Deterministic planner, capability registry, plan validation |
| `test_llm_planner.py` | Unknown metrics, datapoint identifiers, factual figures, invalid weights, fallback |
| `test_plan_execution.py` | The approval gate against a mocked Atlas transport; trace authority |
| `test_sensitivity.py` | Strategy profiles, hashes, influences, flip points, diffs |
| `test_revision.py` | Revision parsing, versioning, and the confirmation requirement |
| `test_workflow.py` | Legal and illegal stage transitions |
| `test_ui.py` | The real Streamlit script at every stage, via `streamlit.testing` |

All twelve scenarios required by the specification are covered, including the ones where
the correct behaviour is to refuse.

### Known limitations

- The revision parser is deterministic pattern matching. It reads the documented phrasings
  and declines rather than guessing on anything else, which is the right failure direction
  but means an unusual phrasing produces "I could not read that as a change" instead of a
  proposal.
- Clarification answers re-plan from scratch rather than incrementally, so a long
  clarification loop re-runs the planner each round. Correct, and cheap at this scale.
- Workflow state lives in the Streamlit session. Plan lineage is not persisted across a
  browser refresh.
- The flip-point scan moves one category weight at a time. Interaction effects between two
  simultaneous weight changes are not explored.
- Sensitivity profiles use the full registry weighting within each category; per-metric
  overrides carried by a plan are respected, but the profiles do not vary them.

### Recommended next increment

Propagate uncertainty. Atlas publishes margins of error and the model already captures
them; turning scores into intervals and withholding a ranking whose intervals overlap
generalises the near-tie gate that already exists, and it is the last place where the
system can still look more confident than the evidence supports.

---

## 0.1.0 — Evidence-bound region comparison

- Verified metric registry: 1,759 candidate datapoints discovered from StateBook's public
  topic configuration, 662 confirmed live, 15 curated across five retail categories. The
  registry refuses to load an unverified identifier.
- Atlas client with bounded retries, timeouts, credential redaction, and raw-call capture.
- Comparability validation: schema, shared-parent geography, period, source, unit, and
  coverage gates, with every exclusion explained and its weight redistribution disclosed.
- Deterministic scoring with min-max and rank normalization, two-stage weight
  renormalization, and a SHA-256 reproducibility hash.
- Evidence-sufficiency gate, including a relative-gap check that catches the degenerate
  two-candidate case where min-max normalization manufactures a decisive-looking spread.
- Refusal behaviour for company-specific forecasts, prompt injection, insufficient
  geographies, API failure, and insufficient evidence.
- Evidence-bound narrator and conversational assistant, both numerically verified against
  the evidence, both fully functional with no LLM key.
- Streamlit interface: recommendation, comparison dashboard, evidence panel, trace, and
  limitations.
