# Architecture: agentic versus deterministic responsibilities

## The governing principle

An agent that can both *decide what to look up* and *decide what is true* has no
meaningful accuracy guarantee, because the second capability can always paper over
failures in the first. This system splits those two powers apart and gives the language
model only the first.

Concretely:

| The agentic layer may | The agentic layer may not |
| --- | --- |
| Interpret a business question | Emit a factual value |
| Interpret a *retail strategy* into a plan proposal | Approve or execute that proposal |
| Ask a clarifying question | Answer it on the user's behalf |
| Classify a request as answerable or not | Emit an Atlas datapoint identifier |
| Select geographies from an allowlist | Select an arbitrary geography |
| Select metric ids from the approved registry | Introduce a metric |
| Propose category weights | Apply them without validation |
| Order and orchestrate approved capabilities | Change what a capability returns |
| Propose a revision to an approved analysis | Apply one without confirmation |
| Recommend an unavailable capability as a next step | Behave as though it ran |
| Explain a validated result | Perform arithmetic |
| Decide that a question should be refused | Decide that a refusal should be overridden |

Every factual claim in the output originates in an `EvidenceItem`, which exists only
because an Atlas response produced it. There is no code path that constructs an
`EvidenceItem` from anything else.

---

## End-to-end flow

```
Business request (natural language)
        |
        v
Agentic strategy interpretation        planning/planner.py  ->  llm_planner | deterministic
        |
        v
Clarification loop (max 3 material questions per round)
        |
        v
Typed analysis-plan proposal           models/plan.py :: AnalysisPlanProposal
        |
        v
Deterministic plan validation          planning/validation.py
        |
        v
Human approval                         orchestration/workflow.py :: approve_and_run
        |
        v
Governed capability orchestration      planning/capabilities.py
        |
        v
Atlas + deterministic analytical services   api/ -> validation/ -> scoring/
        |
        v
Evidence sufficiency                   scoring/sufficiency
        |
        v
Evidence-bound explanation             explanation/narrator.py
        |
        v
Conversational revision proposal       planning/revision.py  (inert)
        |
        v
Human confirmation and versioned rerun orchestration/workflow.py :: confirm_revision
```

Only two edges in that diagram can reach Atlas, and both sit immediately below a human
approval step. Everything above them manipulates a proposal.

After an approved Atlas run, exploratory tools may load public-market archetypes, run the
NorthStar simulator, or search analog stores. Those paths never rewrite Atlas evidence and
never claim unavailable capabilities (foot traffic, ROI forecasting, etc.) executed.

---

## Layers

### 1. Intent and orchestration (`orchestration/`)

The least trusted component, given the narrowest authority. It reads untrusted text, so
its output is treated as a *proposal* that the pipeline re-validates before acting.

`intent.py` sanitizes input (control characters stripped, length capped at 2,000
characters) and then classifies it against three pattern families:

- **Instruction-override patterns** — attempts to disable evidence requirements, reveal
  credentials, or request fabricated numbers. Matching text is refused outright and is
  never used to influence tool selection.
- **Company-specific forecast patterns** — ROI, payback, revenue, profitability, NPV, IRR.
  Atlas describes areas, not businesses, so these are refused with the specific inputs a
  real answer would require.
- **Unsupported dimension mentions** — foot traffic, competitors, rent, cannibalization,
  transaction data. These do not block the analysis; they are recorded as a limitation so
  the gap is visible rather than silently ignored.

Geography resolution is lookup-only. Free text is matched against an alias table derived
from the token's licensed regions; an unmatched name raises `UnsupportedGeographyError`
rather than being coerced into a plausible-looking slug. This is what keeps a
prompt-injected string from reaching the API as a geography parameter.

Metric selection can only return ids that exist in the registry. A test asserts that even
a *real Atlas datapoint identifier* is rejected when supplied as a metric id, because the
identifier namespace and the metric namespace are deliberately separate: the agent works
in metric ids, and only the registry maps those to Atlas identifiers.

`pipeline.py` runs a fixed sequence — interpret, resolve, select, fetch, validate, score,
assess sufficiency, explain — appending a `TraceEntry` at each step. The sequence is not
model-controlled; the model influences only the contents of steps one to three.

### 1b. Planning (`planning/`)

Where the agent's authority actually lives, and where it is bounded. See
[`agentic_planning.md`](agentic_planning.md) for the lifecycle in full; the architectural
points are these.

The planner receives a **capability brief** — supported geographies, approved metric ids
with their categories, units, directions and retail rationales, the deterministic
operations available, and the data dimensions known to be absent. It returns a strict
typed schema. Every field of that schema is then revalidated: metric ids against the
registry, geographies against the allowlist, weights against a range and a sum, and prose
fields against two detectors that reject anything looking like an Atlas datapoint
identifier or a factual figure. A rejected field is recorded on `PlannerProvenance` and
shown in the UI, because a silent rejection is indistinguishable from a model that never
misbehaves.

The deterministic planner produces the same object from pattern matching. It is not a
degraded mode: it is the reference implementation, and the LLM planner's output is merged
onto a deterministic baseline rather than replacing it. Any failure — invalid JSON, a
model error, a rejected field — falls back to that baseline.

`capabilities.py` is the governed tool registry. Available capabilities describe what the
agent may orchestrate; unavailable ones describe foot traffic, competitor locations,
cannibalization, transaction data, real-estate costs, trade areas, and forecasting, each
with the data it would require and the provider type that would supply it. The agent may
recommend one as a next step. There is no code path by which it can claim one ran.

`revision.py` turns a conversational request into a `PlanRevisionProposal` and stops.
Parsing is deterministic pattern matching for the same reason the flip-point scan is: an
approximately-correct reading of "reduce" would be worse than no reading at all.

### 1c. Workflow (`orchestration/workflow.py`)

The plan lifecycle as an explicit state machine — `DESCRIBE`, `CLARIFY`, `REVIEW`,
`EXECUTED`, `REFUSED` — with a fixed transition set and a `WorkflowError` for anything
else. `approve_and_run` is unreachable from `CLARIFY`; a revision cannot execute without
passing back through approval; a human edit is recorded as a `PlanEdit` and revalidated
rather than trusted.

This is deliberately not an autonomous loop. The interesting property of a governed agent
is not that it decides what to do next, it is that a reader can point at any state and say
how it got there and who authorized the move. A state machine makes that a matter of
reading the transition table. It also means the guarantees are tested against the state
machine rather than against an interface, which cannot enforce anything a crafted request
could bypass.

The module has now been driven by two entirely different frontends without a rule changing
in it, which is the clearest evidence available that the boundary is in the right place.

### 1d. HTTP transport (`server/`)

A thin FastAPI layer. Each endpoint resolves a session, calls exactly one transition, and
projects the result; the rules stay in the state machine.

The split introduced one problem the single-process build did not have. When the workflow
state lived in the Python process, `PlanStatus.APPROVED` was unforgeable because nobody
outside the process could construct one. Over HTTP, that has to be re-established, and it
is re-established by refusing to accept state at all: the client holds an opaque session
id, the server holds the plan, and every route is a request to attempt a transition. There
is no endpoint that takes an `AnalysisPlanProposal`, and `tests/test_api.py` asserts that
against the generated OpenAPI schema so a future route cannot quietly reintroduce one.

Locking is per session rather than per store, which is a correctness point disguised as a
performance one. Serializing a session's own transitions is what stops a double-clicked
approve from running the pipeline twice against one human decision. Serializing *across*
sessions buys nothing and costs everything: an Atlas run takes seconds, and a shared lock
would put every other user behind it, which the browser reports the same way it reports a
dead server.

`server/views.py` is the projection layer. Most domain types are Pydantic and serialize
themselves, but a `@property` does not, and computed values like `can_approve`,
`is_usable`, and `completeness` are exactly what the UI needs in order to disable a control
or grey out a row. Each is evaluated in Python and transmitted as a field rather than
reimplemented in TypeScript, so there is one definition of "approvable" rather than two
free to drift apart.

### 2. Atlas API client (`api/`)

Owns authentication, timeouts, bounded retries, and error translation. It knows nothing
about retail or scoring.

- The token is read from the environment, never hardcoded, and lives only in a request
  header. It is stripped from the `RawCall` record before storage.
- Retries are bounded (default 2, capped at 5) with exponential backoff, and only for
  429 and 5xx. A 4xx is a malformed request; retrying it wastes the caller's quota.
- Atlas can report failures inside an HTTP 200 body, so both the status code and an
  `error` object are checked.
- Every call is recorded as a `RawCall` with the request, response, status, attempt count,
  and elapsed time, credential-redacted. The evidence panel renders these directly.

`parsing.py` normalizes the several documented response shapes — single-geography versus
multi-geography, `period`/`value` versus `periods`/`values`, scalar versus nested
collection — into a flat `Observation`. Every consumer works off `Observation`, so no
other module has to reach into raw JSON. Crucially, `Observation` preserves
`reported_geography`, the geography Atlas *actually answered with*, which is what makes
context-shift detection possible.

### 3. Metric registry (`metrics/`)

Maps human-readable retail dimensions to verified Atlas identifiers, with unit,
direction, weight, source, expected periods, supported geographic levels, normalization
method, and a written rationale for why a retailer should care.

The structural guarantee lives here: `MetricRegistry.load()` compares every entry against
`data/atlas_verified_datapoints.json` and raises `UnverifiedMetricError` if any datapoint
lacks a verification record. A hallucinated identifier cannot become a metric, and a
metric is the only thing the orchestrator can request. This is defence in depth with the
API itself, which rejects unknown identifiers with `Unknown datapoint specified`.

### 4. Validation layer (`validation/`)

Decides whether values may share an axis. Detailed rules are listed in the README; the
design point is that **failures are marked and explained, never dropped**. An excluded
metric appears in the evidence panel with its status and reason, and its weight
redistribution is disclosed.

Two rules are worth singling out because they catch failures that a naive implementation
would report as confident results:

- **Shared parent geography.** County Business Patterns is not published below county
  level. Ask for retail establishments in Burlington and Winooski and Atlas returns the
  same Chittenden County figure for both. Without this rule the metric would contribute an
  identical value to every candidate while appearing to be real evidence.
- **Counts across geographic levels.** Comparing a city's population to a county's
  measures which polygon is bigger, not which market is better. Counts are excluded when
  levels are mixed; rates survive with the mismatch disclosed.

### 5. Deterministic scoring (`scoring/`)

Pure functions over floats. No model involvement, no I/O, no randomness.

Aggregation is bottom-up and every intermediate value is retained on a `ScoreBreakdown`:

```
raw value -> normalized 0-100 -> weighted within category -> category score
category scores -> weighted by category weight -> overall score
```

Weights are renormalized twice, and both adjustments are disclosed: within a category over
the metrics that survived for that region, and across categories over the categories that
produced a score. This is what lets a region with a data gap still be scored without
silently treating the missing metric as a zero.

Edge cases are handled explicitly rather than by exception:

| Case | Behaviour |
| --- | --- |
| All candidates share a value | All receive the neutral score of 50, not 0 or 100 |
| A metric is missing for one region | That region is scored on the rest, weights renormalized |
| A metric is missing everywhere | Excluded, weight redistributed, adjustment disclosed |
| Lower is better | Score inverted after normalization |
| One extreme outlier | `RANK` normalization is available; `MIN_MAX` is the default |

`MIN_MAX` is the default because it preserves the relative size of gaps, which is what a
reader expects when they see a bar chart. `RANK` is offered for outlier-heavy sets.
Z-score clamping was considered and rejected: a z-score is bounded by √(n−1), so clamping
at two standard deviations never activates for the small candidate sets this tool exists
to compare.

Reproducibility is attested by a SHA-256 fingerprint over the geographies, category
weights, metric definitions, and every observed value with its period, source, and
validation status. Two runs over the same evidence produce the same hash; a test asserts
it.

#### Sensitivity (`scoring/sensitivity.py`)

A single ranking answers "which region wins under these weights". It does not answer the
question an executive actually has, which is whether that is a fact about the market or a
fact about the weights. Three documented profiles — growth-focused,
purchasing-power-focused, accessibility-focused — re-score the same evidence package under
different weightings, each producing its own reproducibility hash. A flip-point scan then
walks one category weight at a time to find what it would take to reverse the top two.

None of this is estimated. The profiles run through the same `ScoringService` over the
same `EvidencePackage`; the flip scan is a deterministic sweep at a fixed resolution. The
model is never asked how sensitive something is, because a plausible-sounding answer to
that question is indistinguishable from a correct one.

`orchestration/comparison.py` diffs two plan versions and two results, and attributes the
change to the deterministic inputs that moved. The model may summarize that diff; it does
not produce it.

### 6. Explanation layer (`explanation/`)

Receives the validated evidence package and the scoring output, and nothing else. It never
sees the user's question as an instruction and never calls Atlas.

The default narrator is template-based, so the product is fully functional with no LLM.
When `OPENAI_API_KEY` is set, a model is given a **fact sheet** built from the evidence,
instructed to treat it as data rather than instructions, and forbidden from introducing
figures. Its output is then verified: every number in the generated text is checked
against the set of numbers the evidence supports, and the narrative is **discarded in
favour of the deterministic one** if it introduces any. The rejection is surfaced in the
UI as the narrative's provenance.

This inverts the usual arrangement. The model is not trusted and then spot-checked; it is
untrusted, and its output is admissible only if it survives a mechanical check.

#### The assistant, and why a chat surface is the dangerous one

`assistant.py` adds a conversational guide for non-technical readers. It is the component
most likely to break the guarantee the rest of the system exists to enforce, because a
model that can converse about a result will eventually be asked to estimate something, and
answering is the helpful-seeming move. So it gets the narrator's discipline plus two gates
its input requires.

**Its input is classified before the model is reachable.** Every message runs through the
same injection and forecast detectors the pipeline uses, and a match is answered
deterministically with no model call at all. That ordering is the point: a prompt designed
to talk the model out of its rules never arrives in front of the model. A test asserts
this by configuring a deliberately invalid model name alongside a key — a refusal proves
no call occurred, because a call would have failed loudly.

**Questions about data Atlas does not carry are answered, not deflected.** Rent, foot
traffic, competitors, and cannibalization are the likeliest things an executive asks and
the likeliest place a fabrication would land. Those are detected and answered from a fixed
response that says what is missing, why, and where it would come from. Deterministic
rather than model-written, so the behaviour is identical every time it is demonstrated.

**What the model sees is a context pack, not the system.** It is assembled here from the
registry, the evidence package, the deterministic scores, the exclusions, and the
limitations. There is no path by which the assistant reads an Atlas response or computes
anything, and every value in the pack travels with its datapoint, source, and period
attached, so a grounded answer is also a citable one.

**Output is verified identically to the narrative.** Numbers not present in the context
pack cause the reply to be replaced by a deterministic answer, and the substitution is
shown to the reader rather than hidden.

Without a key the assistant still answers, routing the question to the relevant facts. It
is plainer, but it is grounded in the same pack, so the product has no dependency on an
LLM being configured and no behaviour that only exists when one is.

The session key is collected in the sidebar and held in the browser tab. It travels to the
API as an `X-OpenAI-Key` header and is used to build a `Settings` copy scoped to that one
request. It is never written to the server's session store, to disk, to a log, or into an
exported result; `Settings` is frozen and `with_llm` returns a copy, so a key supplied by
one browser cannot leak into the process defaults or into another user's session.

The browser calls the API directly rather than proxying through a Next.js route handler,
which is a deliberate choice about credential surface: a proxy would add a second process
holding the key in memory and a second request log it could appear in, in exchange for
nothing this application needs.

**The assistant can now propose changes, which is a second control surface.** "Double the
weight on income" is an instruction, and a chat box that carries it out has quietly become
a way to change the answer without an approval step. So a message classified as a revision
request produces a `PlanRevisionProposal` — before/after values, a hedged statement of the
analytical effect, and a deterministic validation report — and nothing else happens. The
classifier sits behind the injection and forecast gates, so no phrasing of "just change
it and run it" reaches a path that would.

### 7. Map-first client (`web/`)

The Next.js workspace is presentation around the same state machine. Map markers are
server-projected centroids; scores and rankings are never recomputed in TypeScript.
Resizable columns are chrome only. Post-execute tabs (Archetypes, Retailer simulation,
Analog stores) call deterministic Python services and render projections with
`DataClass` badges.

### 8. Public market discovery (`market_discovery/`)

A versioned county clustering artifact under `data/market_discovery/v1/`. Features are
ACS-shaped and labeled `PUBLIC_MARKET_DATA`. K-means membership is deterministic for a
fixed seed and config hash; the agent capability `market.archetype_analysis` may look up
and explain results but cannot invent membership. See
[`market_discovery.md`](market_discovery.md) and
[`clustering_methodology.md`](clustering_methodology.md).

### 9. Synthetic retailer twin (`retailer_simulation/`)

Seeded equation-based **NorthStar Apparel** generation anchored to a public benchmark
catalog with verification states (`VERIFIED` / `DEMO_DEFAULT` / `UNVERIFIED_DISABLED`).
Disabled benchmarks never affect generation. Outputs are always
`SIMULATED_RETAILER_DATA`. Stores can be enriched with host-county archetypes so the UI
can profile fictional peers in markets like the selected candidate — demo context, not a
forecast. Capability: `retailer.scenario_simulation`. See
[`synthetic_retailer.md`](synthetic_retailer.md).

### 10. Analog-store matching (`analog_matching/`)

Nearest-neighbor look-alikes between a candidate market and synthetic stores using
**public market features only**. Sales and margin are excluded from the match vector
(outcome leakage forbidden) and appear only after ranking, always labeled simulated.
Capability: `retailer.analog_store_search`. See [`analog_matching.md`](analog_matching.md)
and [`data_provenance.md`](data_provenance.md).

---

## The trace as an accountability record

`TraceEntry` carries a `TraceAuthority`, and the eight values distinguish user-supplied
information, agent inference, deterministic validation, API evidence, human approval,
deterministic calculation, model-generated explanation, and system bookkeeping.

The reason to label authority rather than just sequence is that the log has to answer a
different question from "what happened". It has to answer *who or what authorized this*.
A figure carrying `API` or `CALCULATION` authority came from evidence. One carrying `AGENT`
authority is a proposal that had to survive validation to matter, and the trace shows the
validation entry that either accepted or rejected it. The UI filters on the authority so a
reviewer can read only the decisions a human made, or only the ones the model influenced.

---

## Security boundaries

| Concern | Mitigation |
| --- | --- |
| Secrets in source control | `.env` is gitignored; only `.env.example` is committed; the token is read from the environment |
| Credential leakage into logs or UI | `redact()` recursively strips anything matching auth/token/secret/key patterns, plus `Bearer` headers and `auth=` parameters, from every persisted payload |
| Untrusted input reaching the API | Geographies resolve through an allowlist; metric ids resolve through the registry; neither accepts free text |
| Prompt injection | Detected before planning, before tool selection, and before the assistant's model is called at all; matched requests are refused and the attempt is recorded |
| LLM fabrication | The model receives only a fact sheet, capability brief, or context pack, and its output is numerically verified against the evidence before acceptance |
| Planner fabrication | Every field the planner returns is revalidated against the registry and allowlist; prose fields are scanned for datapoint identifiers and factual figures; rejections are recorded on the plan |
| Execution without authorization | `AnalysisPipeline.run_approved` consults `AnalysisPlanProposal.can_execute`, which requires passing validation, no unanswered required question, `APPROVED` status, *and* an approval record. A forged status alone is refused |
| Conversational control | A revision request produces an inert proposal; only an explicit confirmation creates a new plan version, and that version re-enters approval |
| Claiming an unavailable capability | Unavailable capabilities are data, not code paths. There is no function to call, so the failure mode is a recommendation rather than a simulated result |
| Mixing data classes | Every wire payload for public or simulated numbers carries `DataClass`; UI badges make silent combination a review failure |
| Outcome leakage into analogs | Matching feature registry excludes sales/margin; tests assert forbidden ids are absent |
| Session credentials | An OpenAI key entered in the UI lives in the browser tab and one request scope only: never in local storage, the server session store, disk, a log, or an exported result |
| Client-forged state | The client holds an opaque session id, never a plan. No route accepts a plan object, so approval cannot be asserted from outside the server |
| Cross-session access | Session ids are 128-bit `secrets.token_urlsafe` values and every route resolves state by id; an unknown id is a 404, never an implicit new session |
| Unbounded resource use | Request timeouts, bounded retries, capped input length |
| Silent failure | Atlas errors produce a refusal with the failed call in the trace, never a partial answer presented as complete |

---

## What this architecture does not solve

Worth stating plainly, because a credible prototype should name its own gaps:

- **The pattern-based intent classifier is a prototype control, not a security boundary.**
  It catches the obvious injection and forecast phrasings and will miss novel ones. In
  production this belongs behind a dedicated classifier with adversarial evaluation, and
  the deterministic guarantees below it — allowlists, registry gating, output
  verification — are what actually bound the damage when it misses.
- **Metric direction encodes a business assumption.** "Lower median age is better" is true
  for the assumed retailer profile and false for others. It is documented per metric, but
  it is a judgement, not a fact from the data.
- **Weighted linear scoring is a communication tool, not a causal model.** It says nothing
  about whether these indicators predict store performance. That would require outcome
  data the system does not have.
- **The session store is in-memory and unauthenticated.** It is a dict behind a lock with
  an LRU cap, which is correct for a single-process prototype and wrong for anything
  multi-replica. Sessions do not survive a restart, and holding a session id is the only
  credential required to resume one. Real deployment needs shared storage and an identity
  in front of it; `server/sessions.py` is small and single-purpose precisely so that
  swapping it is a contained change.
- **ACS values are 5-year rolling estimates with margins of error** that widen for smaller
  places. Margins of error are available in Atlas (`.moe`) and are captured in the model,
  but they are not yet propagated into the score as confidence intervals. That is the
  single most valuable next increment to the scoring layer.
