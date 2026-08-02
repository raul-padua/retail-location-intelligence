# Retail Location Intelligence

An evidence-bound agentic prototype that helps a retail strategy or real-estate executive
compare candidate regions for a new store, using real data from the
[StateBook Atlas API](https://statebook.zendesk.com/hc/en-us/articles/360016198753-Authentication-and-Licensing).

The central design constraint: **deterministic analytical services are the source of
truth**. The agent interprets a business objective, constructs a governed analysis plan,
asks what it needs to ask, and explains the result. It cannot invent a value, invent a
datapoint identifier, perform arithmetic, execute an unapproved plan, or present a
recommendation that is not traceable to an API response.

> The agent does not decide which location is best. It collaborates with the user to define
> the decision, constructs a governed analytical plan, identifies missing information,
> orchestrates approved analytical services, and explains the resulting evidence.

> Illustrative scenario only. A GAP-like national apparel retailer is used to make the
> business framing concrete. This prototype uses no proprietary retailer data and is not
> affiliated with, endorsed by, or a client engagement of any retailer.

---

## Quick start

```bash
cd retail-location-intelligence

uv sync --group dev                    # creates .venv and installs everything

cp .env.example .env                   # STATEBOOK_API_TOKEN=demo works out of the box

uv run streamlit run app/streamlit_app.py
```

Then open http://localhost:8501 and describe a decision in your own words, for example:

> *"We are evaluating Burlington, South Burlington, and Winooski for a suburban apparel
> store targeting middle-income families. Prioritize growth and accessibility over current
> market size."*

The agent interprets it, asks anything material it could not infer, and proposes a plan.
Nothing reaches Atlas until you approve that plan.

Run the tests:

```bash
uv run pytest                # 296 offline tests against a mocked Atlas transport
uv run pytest -m live        # 6 integration tests against the real API
```

### The workflow

```
Describe the decision  ->  Clarify  ->  Review the plan  ->  Approve  ->  Result
                                             ^                              |
                                             |                              v
                                    Confirm a revision  <-  Ask to change something
```

Five stages, a fixed set of transitions, and an exception for anything else. Execution is
unreachable from the clarify stage; a plan cannot be approved until it passes deterministic
validation; a revision creates a new version rather than mutating the current one. The
rules live in `app/workflow.py` rather than in the widgets, so a browser rerun cannot get
around them.

Details in [`docs/agentic_planning.md`](docs/agentic_planning.md).

### Optional: the conversational assistant

Paste an OpenAI key into the top of the sidebar to make the planner and the **Assistant**
tab conversational. The key is held in the browser session only; it is never written to
disk, logged, or included in an exported result.

The assistant answers from the evidence the analysis produced, refuses instruction-override
and forecast questions before the model is ever called, and has any reply discarded if it
states a figure the evidence does not contain.

It can also change the analysis — sort of. Ask it to *"double the importance of household
income"* or *"drop median age"* and it writes a typed revision proposal showing exactly
what would change and what the effect would likely be, then waits for you to confirm. A
chat box attached to a live analysis is a control surface whether or not it was designed as
one, so it proposes and stops.

### Configuration

All configuration is environment-based; no credential appears in source. See
`.env.example`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `STATEBOOK_API_TOKEN` | Atlas bearer token. `demo` is the public evaluation token. | none (required) |
| `STATEBOOK_API_BASE_URL` | Atlas base URL. | `https://api.statebook.com` |
| `STATEBOOK_TIMEOUT_SECONDS` | Per-request timeout. | `30` |
| `STATEBOOK_MAX_RETRIES` | Bounded retries after the first attempt, capped at 5. | `2` |
| `OPENAI_API_KEY` | Optional. Enables the narrator and the assistant. Can also be pasted into the sidebar. | unset |
| `RLI_LLM_MODEL` | Model used when a key is present. Overridable in the sidebar. | `gpt-5.6-luna` |
| `RLI_LOG_LEVEL` | Structured log level. | `INFO` |

**The demo works with no LLM key.** Without one, a deterministic planner reads the
objective by pattern matching, and the narrative and assistant are composed from the
evidence. Planning, clarification, approval, revision, sensitivity, and comparison all
behave identically. The language model improves flexibility and phrasing; it is not a
runtime dependency, and the deterministic planner is the reference implementation rather
than a degraded mode.

The default model is the cost tier deliberately. The model never produces a number and
never authorizes anything: it proposes a plan whose every field is revalidated, and it
rewrites a fact sheet whose every figure is verified. Frontier reasoning buys phrasing, not
accuracy. Larger models are selectable in the sidebar if that matters for an audience.

---

## What the demo token can actually do

The public `demo` token licenses only the **Burlington–South Burlington, VT metro area**:
three counties, thirteen cities, one CBSA, and one congressional district. That is a real
constraint, not a simplification, and the application treats it as one: the geography
allowlist is derived from it, requests outside it are refused rather than attempted, and
the limitation is stated in the UI.

---

## How the data was discovered

Atlas documents over a thousand datapoints but publishes the list as
"[URL to be determined]". The catalogue was therefore discovered and then verified:

| Step | Command | Result |
| --- | --- | --- |
| Discover candidates | `uv run python scripts/crawl_atlas_catalog.py` | 1,759 candidate identifiers from the public Calypso topic configuration |
| Verify against the live API | `uv run python scripts/verify_datapoints.py` | 662 confirmed to return a value |
| Curate for retail relevance | `metrics/registry.py` | 15 metrics across 5 categories |
| Regenerate the metric document | `uv run python scripts/generate_metric_doc.py` | [`docs/metric_registry.md`](docs/metric_registry.md) |

`MetricRegistry.load()` re-checks every entry against the verification artifact at import
time and **raises rather than loading** if a datapoint has no verification record. Atlas
itself is the last line of defence: an unknown identifier is rejected with
`Unknown datapoint specified`.

---

## Architecture at a glance

```
              business objective (untrusted text)
                       |
   [0] Planning ..................... interprets strategy, proposes metrics and weights,
                       |               asks material questions, names what it cannot do
                       |               may NOT emit values, datapoints, or a ranking
   [0b] Plan validation ............. deterministic gate; produces an approvable plan
                       |
   [0c] Human approval .............. the only route to an Atlas call
                       |
   [1] Intent & orchestration ....... resolves the approved plan into tool calls
                       |
   [2] Atlas API client ............. auth, timeouts, bounded retries, raw-call capture
                       |
   [3] Metric registry .............. verified datapoints only; refuses to load otherwise
                       |
   [4] Validation layer ............. schema, geography, period, source, unit, coverage
                       |
   [5] Deterministic scoring ........ normalization, weighting, ranking, sensitivity,
                       |               reproducibility hash
   [6] Explanation layer ............ sees only the validated evidence package
                       |               narrator and assistant, both output-verified
                       |
   [7] Revision proposal ............ inert until confirmed; confirming creates version n+1
```

Full discussion of which responsibilities are agentic and which are deterministic, and why:
[`docs/architecture.md`](docs/architecture.md). The plan lifecycle, clarification policy,
and agent authority boundaries: [`docs/agentic_planning.md`](docs/agentic_planning.md).

### Project layout

```
app/             Streamlit interface and the typed workflow state machine
api/             Atlas client, response parsing, geography allowlist
planning/        Agentic planner (LLM and deterministic), capability registry,
                 plan validation, revision proposals
orchestration/   Intent classification, refusal policy, evidence fetching, pipeline,
                 plan and result comparison
metrics/         Approved metric registry and its verification gate
validation/      Comparability gates
scoring/         Deterministic normalization, weighted scoring, strategy profiles,
                 sensitivity and flip-point analysis
explanation/     Evidence-bound narrator and chat assistant, both output-verified
models/          Typed pydantic models shared by every layer
core/            Environment configuration and credential-redacting logging
scripts/         Catalogue discovery, datapoint verification, sample and doc generation
tests/           296 offline tests, 6 live integration tests
docs/            Architecture, agentic planning, metric registry, demo, productionization
sample_outputs/  Committed successful and refusal outputs
data/            Discovered candidates and the verification record
```

---

## The refusal behaviour

The system refuses rather than guesses. Ask *"Which city will generate the highest
five-year ROI for GAP?"* and it explains that Atlas publishes observable market
indicators for geographic areas and holds no information about a retailer's economics,
then lists the ten inputs a genuine answer would require (store format, rent and
construction cost, cannibalization, foot traffic, competitor locations, transaction data,
gross margin, supply-chain cost, marketing assumptions, and an approved forecasting
methodology), and offers the supported comparison instead.

Distinct conditions produce a refusal:

| Condition | Behaviour |
| --- | --- |
| Company-specific financial forecast | Refuse before a planner runs, list required inputs, offer the indicator comparison |
| Prompt injection | Refuse before a planner runs; explain that user text is data and never instructions; record the attempt |
| Fewer than two licensed regions | Refuse, name the rejected inputs and the token's footprint |
| Atlas unreachable or no token | Refuse; there is no fallback data source and no estimation path |
| Evidence insufficient to separate candidates | Withhold the ranking, still show the evidence |
| Requested dimension has no approved metric | Disclose it on the plan with the capability and data source that would supply it |
| Unavailable future capability requested | Show it as unavailable with its integration path; never simulate a result |
| Plan not approved, or approval forged | `PlanNotApprovedError` before any request object is constructed |

The last one is the subtle case. With two candidate regions, min-max normalization always
places one at 100 and the other at 0 on every metric, no matter how trivial the underlying
difference. The sufficiency gate therefore also checks the **median relative gap between
the top two regions' raw values**, and withholds the ranking when it falls below 1% — the
score would look decisive while the regions are indistinguishable.

See [`sample_outputs/`](sample_outputs/) for committed examples of every case.

---

## What makes a number trustworthy here

- **Every value carries provenance.** Each `EvidenceItem` records the Atlas datapoint id,
  the geography requested, the geography Atlas actually answered with, the period, the
  source, the validation status, and the id of the API call it came from.
- **Every score is reproducible.** The scoring service emits a SHA-256 fingerprint over
  the geographies, weights, metric definitions, and observed values. The same inputs
  always produce the same hash and the same ranking.
- **Every exclusion is explained.** A metric that fails a comparability gate appears in
  the evidence panel with the reason, and its weight is redistributed with the adjustment
  disclosed.
- **Credentials never leak.** Tokens are stripped from every persisted request, response,
  and log line before storage, and tests assert it.
- **Every decision has an author.** Each trace entry carries an authority — user-supplied,
  agent inference, deterministic validation, API evidence, human approval, deterministic
  calculation, model-generated explanation — so the log answers *who authorized this*, not
  just *what happened*.
- **Every analysis has an approved plan behind it.** The executed `AnalysisPlanProposal` is
  attached to the result, with its assumptions, disclosed gaps, human edits, and approval
  record.
- **The answer is stress-tested, not just produced.** Three documented strategy lenses
  re-score the same evidence, and a flip-point scan reports what it would take to reverse
  the top two — so you can tell whether the recommendation is a fact about the market or a
  fact about the weights.

### Comparability gates

Two numbers existing is not the same as two numbers being comparable. Per metric, across
the candidate set:

1. **Schema** — the value must be numeric and carry a reporting period.
2. **Geography** — Atlas must not have widened the context for some regions but not
   others. A metric that resolves to one shared parent geography for every candidate is
   excluded, because it would assign every region the same number.
3. **Period** — reporting periods must agree within the configured tolerance (default 0).
4. **Source** — values must come from the same Atlas source.
5. **Unit** — a metric declared as a share must behave like one. Counts are excluded when
   the candidates span different geographic levels, since a county necessarily reports a
   larger count than a city inside it. Rates survive, with the mismatch disclosed.
6. **Coverage** — at least two regions must retain a usable value.

---

## Deliverables

| Deliverable | Location |
| --- | --- |
| Working local application | `app/streamlit_app.py` |
| Architecture: agentic vs deterministic | [`docs/architecture.md`](docs/architecture.md) |
| Agent authority, plan lifecycle, fallbacks | [`docs/agentic_planning.md`](docs/agentic_planning.md) |
| Verified metric registry | [`docs/metric_registry.md`](docs/metric_registry.md) |
| Seven-minute demo script | [`docs/demo_script.md`](docs/demo_script.md) |
| Path to a production platform | [`docs/productionization.md`](docs/productionization.md) |
| Change log | [`CHANGELOG.md`](CHANGELOG.md) |
| Unit, integration, and UI tests | `tests/` |
| Sample successful and refusal outputs | [`sample_outputs/`](sample_outputs/) |

---

## Attribution and licensing

Data is retrieved from the StateBook Atlas API and is subject to StateBook's licensing
terms, which the API restates on every response: *"The data returned from this StateBook
Data API call is restricted and may only be used in accordance with the terms of a current
and valid StateBook Data API license."* Underlying sources are attributed per metric in
the evidence panel and in the metric registry document, and are principally the US Census
Bureau (American Community Survey and County Business Patterns).
