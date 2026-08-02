# Retail Location Intelligence

An evidence-bound agentic prototype that helps a retail strategy or real-estate executive
compare candidate regions for a new store, using real data from the
[StateBook Atlas API](https://statebook.zendesk.com/hc/en-us/articles/360016198753-Authentication-and-Licensing).

The central design constraint: **deterministic analytical services are the source of
truth**. The agentic layer interprets the question, picks approved tools, and explains
results. It cannot invent a value, invent a datapoint identifier, perform arithmetic, or
present a recommendation that is not traceable to an API response.

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

Then open http://localhost:8501, pick a preset scenario in the sidebar, and select
**Run analysis**.

Run the tests:

```bash
uv run pytest                # 103 offline tests against a mocked Atlas transport
uv run pytest -m live        # 6 integration tests against the real API
```

### Optional: the conversational assistant

Paste an OpenAI key into the top of the sidebar to enable the **Assistant** tab, a chat
guide for non-technical readers. The key is held in the browser session only; it is never
written to disk, logged, or included in an exported result.

The assistant is bound by the same rules as everything else: it answers only from the
evidence the analysis produced, refuses instruction-override and forecast questions before
the model is ever called, and has any reply discarded if it states a figure the evidence
does not contain. Without a key it still works, assembling answers from the same evidence
in plainer language.

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

**The demo works with no LLM key.** Without one, the narrative and the assistant are
composed deterministically from the evidence. With a key, a model rewrites text that is
already grounded, and its output is rejected if it introduces a figure the evidence does
not contain.

The default model is the cost tier deliberately. The model here never produces a number
and never decides anything; it rewrites a fact sheet and its output is verified either
way, so frontier reasoning buys little. Larger models are selectable in the sidebar if the
phrasing matters for a particular audience.

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
                 untrusted text
                       |
   [1] Intent & orchestration ....... may pick approved geographies and metric ids
                       |               may NOT emit values, datapoints, or arithmetic
   [2] Atlas API client ............. auth, timeouts, bounded retries, raw-call capture
                       |
   [3] Metric registry .............. verified datapoints only; refuses to load otherwise
                       |
   [4] Validation layer ............. schema, geography, period, source, unit, coverage
                       |
   [5] Deterministic scoring ........ normalization, weighting, ranking, reproducibility hash
                       |
   [6] Explanation layer ............ sees only the validated evidence package
                       |               narrator and assistant, both output-verified
                  cited narrative
```

Full discussion of which responsibilities are agentic and which are deterministic, and why:
[`docs/architecture.md`](docs/architecture.md).

### Project layout

```
app/             Streamlit interface (six panels plus the assistant)
api/             Atlas client, response parsing, geography allowlist
orchestration/   Intent classification, refusal policy, evidence fetching, pipeline
metrics/         Approved metric registry and its verification gate
validation/      Comparability gates
scoring/         Deterministic normalization and weighted scoring
explanation/     Evidence-bound narrator and chat assistant, both output-verified
models/          Typed pydantic models shared by every layer
core/            Environment configuration and credential-redacting logging
scripts/         Catalogue discovery, datapoint verification, sample and doc generation
tests/           103 offline tests, 6 live integration tests
docs/            Architecture, metric registry, demo script, productionization
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

Five distinct conditions produce a refusal:

| Condition | Behaviour |
| --- | --- |
| Company-specific financial forecast | Refuse, list required inputs, offer the indicator comparison |
| Prompt injection | Ignore the instruction, refuse, explain that user text is data and never instructions |
| Fewer than two licensed regions | Refuse, name the rejected inputs and the token's footprint |
| Atlas unreachable or no token | Refuse; there is no fallback data source and no estimation path |
| Evidence insufficient to separate candidates | Withhold the ranking, still show the evidence |

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
| Verified metric registry | [`docs/metric_registry.md`](docs/metric_registry.md) |
| Five-minute demo script | [`docs/demo_script.md`](docs/demo_script.md) |
| Path to a production platform | [`docs/productionization.md`](docs/productionization.md) |
| Unit and integration tests | `tests/` |
| Sample successful and refusal outputs | [`sample_outputs/`](sample_outputs/) |

---

## Attribution and licensing

Data is retrieved from the StateBook Atlas API and is subject to StateBook's licensing
terms, which the API restates on every response: *"The data returned from this StateBook
Data API call is restricted and may only be used in accordance with the terms of a current
and valid StateBook Data API license."* Underlying sources are attributed per metric in
the evidence panel and in the metric registry document, and are principally the US Census
Bureau (American Community Survey and County Business Patterns).
