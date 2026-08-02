# Change log

## 0.3.0 — Next.js client over a governed API

The frontend moves from Streamlit to Next.js. No rule changed, which was the point: the
guarantees were already in the state machine and the pipeline, so replacing the interface
was a transport exercise rather than a rewrite of anything that decides something.

One property did have to be rebuilt. In a single Python process, `PlanStatus.APPROVED` was
unforgeable because nobody outside the process could construct one. Across a network, that
has to be re-earned, and it is re-earned by never accepting state from the client at all.

### Added

**An HTTP API (`server/`)**

- `server/app.py` — FastAPI over the existing workflow. Each route resolves a session,
  calls exactly one transition, and projects the result. There is no business logic in it.
- `server/sessions.py` — a thread-safe, LRU-capped session store holding `WorkflowState`
  server-side. The client receives a 128-bit opaque id and nothing else. **No route accepts
  a plan object**, so a client cannot assert approval, edit a validation report, or hand
  back a plan with `status` flipped. `tests/test_api.py` asserts this against the generated
  OpenAPI schema so a future route cannot quietly reintroduce one.
  Locking is per session, not per store. A session's own transitions serialize — a
  double-clicked approve gets one 200 and one 409, never two versions for one decision —
  while a slow Atlas run in one session leaves every other session free. A single shared
  lock passes all the behavioural tests and still stalls the server behind its slowest
  request, so the test asserts the property directly: a mocked transport waits on a
  two-party barrier that can only be satisfied if both sessions are inside the pipeline at
  once. Eviction skips sessions that are mid-request and overshoots the cap instead.
- `server/views.py` — the projection layer. Computed properties (`can_approve`,
  `is_usable`, `completeness`) are evaluated in Python and sent as fields rather than
  reimplemented in TypeScript, so "approvable" has one definition rather than two free to
  drift apart.
- `server/schemas.py` — typed request bodies. The catalog endpoint serves the presets,
  objective examples, and model choices that were previously constants inside the UI file,
  which keeps the licensed-geography list on the server that enforces it.

**A Next.js client (`web/`)**

- TypeScript, Tailwind, and Recharts. Stage screens for describe, clarify, review, and
  refused; result panels for the recommendation, dashboard, evidence, plan, trace,
  limitations, registry, sensitivity, versions, and the assistant.
- `web/src/lib/types.ts` mirrors the server's projections as compile-time contracts.
- `scripts/generate_web_fixtures.py` drives the real FastAPI app against the same mocked
  Atlas transport the Python tests use and emits **typed** fixtures. Because each fixture is
  annotated, `npm run typecheck` compares the actual projection against the declared
  contract and turns schema drift into a build failure instead of an `undefined` in a panel.
- `scripts/dev.sh` runs both processes.

### Changed

- `app/workflow.py` → `orchestration/workflow.py`. The state machine was never UI code, and
  leaving it in a directory named `app/` next to a deleted Streamlit script would have
  implied otherwise.
- The OpenAI key is entered in the browser, sent per-request as an `X-OpenAI-Key` header,
  and used to build a request-scoped `Settings` copy. It is never written to local storage,
  the session store, disk, a log, or an exported result. The browser calls the API directly
  rather than proxying through a Next.js route handler, which would add a second process
  holding the key and a second log it could surface in, for no benefit here.
- Removed `streamlit`, `pandas`, `altair`, and `watchdog`.
- The CORS allowlist is configurable via `RLI_CORS_ORIGINS`, and `scripts/dev.sh` derives it
  from `WEB_PORT`. It was hardcoded to port 3000, so running the client anywhere else failed
  every request in preflight and surfaced in the UI as "cannot reach the analysis service" —
  a symptom that points at the wrong process entirely. A wildcard is still not accepted: the
  API takes an OpenAI key in a header, so any-origin access would forward credentials.
- The narrator and assistant emit `**bold**`, which the previous frontend rendered as
  markdown and this one was printing literally. Added a two-construct renderer rather than a
  markdown library, since some of that text comes from a model and a real markdown parser
  would also happily render links and raw HTML.
- Copy that referred to editing weights "in the sidebar" now describes the plan-edit and
  revision paths, which is where weights are actually changed.

### Tests

312 offline Python (up from 296) and 24 frontend.

| Suite | Covers |
| --- | --- |
| `tests/test_api.py` | Every transition over HTTP, the approval gate, session isolation, header-scoped credentials, concurrent access, and the absence of any plan-accepting route |
| `web/src/components/Workspace.test.tsx` | Stage routing, the disabled approve control, provenance rendering, revision confirmation, result panels, and credential handling |
| `web/scripts/browser_smoke.mjs` | The full arc in a real browser against a running API, failing on any console error. Not part of `npm test`; it needs both processes up |

`tests/test_ui.py` is gone; `tests/test_workflow.py` covered the guarantees it was really
testing, and it now does so without a UI in the way.

### Known limitations

- The session store is in-memory and unauthenticated: single-process only, lost on restart,
  and holding a session id is the only credential needed to resume one. It is deliberately
  small and single-purpose so that swapping it for shared storage behind an identity is a
  contained change.

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
