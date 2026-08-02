"""Retail Location Intelligence - founder demo UI.

Six panels, in the order an executive reads them: scenario setup, the recommendation,
the comparison dashboard, the evidence behind every number, the full execution trace, and
the limitations. The UI renders what the pipeline produced and computes nothing itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import altair as alt
import pandas as pd
import streamlit as st

from api.geographies import DEMO_TOKEN_SCOPE_NOTE, demo_geography_choices
from core.config import DEFAULT_LLM_MODEL, Settings, get_settings
from explanation.assistant import ask, build_context
from metrics.registry import UnverifiedMetricError, get_registry
from models.analysis import AnalysisResult, LimitationSeverity
from models.evidence import ValidationStatus
from models.metrics import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_LABELS,
    CATEGORY_WEIGHT_GUIDANCE,
    MetricCategory,
    Unit,
)
from orchestration.pipeline import AnalysisPipeline, AnalysisRequest
from scoring.service import DEFAULT_CATEGORY_WEIGHTS

st.set_page_config(
    page_title="Retail Location Intelligence",
    page_icon="RL",
    layout="wide",
)

PRESETS: dict[str, list[str]] = {
    "Urban core vs suburbs (4 cities)": [
        "city:burlington-vt",
        "city:south-burlington-vt",
        "city:winooski-vt",
        "city:williston-vt",
    ],
    "County-level market screen (3 counties)": [
        "county:chittenden-county-vt",
        "county:franklin-county-vt",
        "county:grand-isle-county-vt",
    ],
    "Head-to-head (2 cities)": ["city:burlington-vt", "city:winooski-vt"],
    "Mixed geographic levels (city vs county)": [
        "city:burlington-vt",
        "county:franklin-county-vt",
    ],
}

# The model only rewrites grounded text and its output is verified against the evidence, so
# the cheap tier is the sensible default; the larger models are offered for phrasing quality.
LLM_MODEL_CHOICES: dict[str, str] = {
    "gpt-5.6-luna": "Cost-optimized. Recommended: the model's job here is narrow.",
    "gpt-5.6-terra": "Balanced. Better phrasing on open-ended assistant questions.",
    "gpt-5.6-sol": "Frontier. Rarely worth it for this workload.",
    "gpt-5.4-mini": "Previous generation, small.",
    "gpt-4o-mini": "Legacy. Still works; two generations behind.",
}

STATUS_LABELS = {
    ValidationStatus.VALID: "Valid",
    ValidationStatus.MISSING: "Missing",
    ValidationStatus.SCHEMA_INVALID: "Schema invalid",
    ValidationStatus.INCOMPARABLE_PERIOD: "Incomparable period",
    ValidationStatus.INCOMPARABLE_GEOGRAPHY: "Incomparable geography",
    ValidationStatus.INCOMPARABLE_UNIT: "Incomparable unit",
    ValidationStatus.INCOMPARABLE_SOURCE: "Incomparable source",
}


def format_value(value: float | None, unit: Unit) -> str:
    if value is None:
        return "-"
    if unit == Unit.PERCENT:
        return f"{value * 100:.1f}%"
    if unit == Unit.USD:
        return f"${value:,.0f}"
    if unit == Unit.YEARS:
        return f"{value:.1f} yrs"
    if unit == Unit.MINUTES:
        return f"{value:.1f} min"
    return f"{value:,.0f}"


@st.cache_resource(show_spinner=False)
def load_registry():
    return get_registry()


def assistant_settings() -> Settings:
    """Collect the OpenAI key and model at the top of the sidebar.

    The key lives in Streamlit session state for the life of the browser session only. It
    is never written to disk, never logged, and never included in an exported result. An
    ``OPENAI_API_KEY`` in the environment is used as the default when present.
    """
    base = get_settings()

    with st.sidebar.container(border=True):
        st.markdown("**AI assistant**")

        from_env = bool(base.openai_api_key)
        entered = st.text_input(
            "OpenAI API key",
            value=st.session_state.get("openai_key", base.openai_api_key or ""),
            type="password",
            placeholder="sk-...",
            help=(
                "Optional. Enables the conversational guide and lets the model rewrite the "
                "recommendation. Held in this browser session only; never written to disk. "
                "Without a key everything still runs, and the narrative and the assistant "
                "are generated deterministically."
            ),
            key="openai_key",
        )

        model = DEFAULT_LLM_MODEL
        if entered.strip():
            options = list(LLM_MODEL_CHOICES)
            default_model = base.llm_model if base.llm_model in options else DEFAULT_LLM_MODEL
            model = st.selectbox(
                "Model",
                options,
                index=options.index(default_model),
                format_func=lambda name: name,
                help="The model never produces a figure; it rewrites text that is already grounded.",
            )
            st.caption(LLM_MODEL_CHOICES[model])
            st.success(
                "Assistant enabled" + (" (key from environment)" if from_env else " (session key)")
            )
        else:
            st.caption(
                "No key set. The assistant and the narrative fall back to deterministic "
                "text built from the same evidence."
            )

    return base.with_llm(entered, model)


def sidebar(settings: Settings) -> tuple[AnalysisRequest, bool]:
    st.sidebar.title("Scenario setup")

    if settings.atlas_token:
        st.sidebar.success(
            f"Atlas token configured{' (public demo token)' if settings.is_demo_token else ''}"
        )
    else:
        st.sidebar.error("STATEBOOK_API_TOKEN is not set. Copy .env.example to .env.")

    st.sidebar.caption(DEMO_TOKEN_SCOPE_NOTE)

    st.sidebar.subheader("1. Candidate regions")
    preset = st.sidebar.selectbox("Preset scenario", list(PRESETS), index=0)
    choices = demo_geography_choices()
    labels = {geography.slug: geography.display_name for geography in choices}
    selected = st.sidebar.multiselect(
        "Regions to compare",
        options=list(labels),
        default=PRESETS[preset],
        format_func=lambda slug: labels.get(slug, slug),
        help="Only regions licensed by the active token can be selected.",
    )

    st.sidebar.subheader("2. Retailer profile")
    profile = st.sidebar.selectbox(
        "Strategic priority",
        [
            "National mainstream apparel retailer (GAP-like)",
            "Youth and campus-oriented apparel banner",
            "Premium apparel banner",
        ],
    )

    st.sidebar.subheader("3. Question")
    question = st.sidebar.text_area(
        "Business question",
        value="Which of these regions appears most attractive for opening a new apparel store?",
        height=90,
    )

    st.sidebar.subheader("4. Category weights")
    st.sidebar.caption(
        "These encode the strategy, so they are yours to set. Weights are renormalized to "
        "sum to 1 before scoring; adjust and re-run to see the ranking recalculated from "
        "the same Atlas values."
    )

    registry = load_registry()
    weights: dict[MetricCategory, float] = {}
    for category, default in DEFAULT_CATEGORY_WEIGHTS.items():
        members = [
            metric.display_name for metric in registry.all() if metric.category == category
        ]
        weights[category] = st.sidebar.slider(
            CATEGORY_LABELS[category],
            0.0,
            1.0,
            float(default),
            0.05,
            help=(
                f"**{CATEGORY_DESCRIPTIONS[category]}**\n\n"
                f"{CATEGORY_WEIGHT_GUIDANCE[category]}\n\n"
                "Measured by: " + ", ".join(members) + "."
            ),
        )
        st.sidebar.caption(CATEGORY_DESCRIPTIONS[category])

    total = sum(weights.values())
    if total <= 0:
        st.sidebar.error("At least one category weight must be greater than zero.")
    else:
        st.sidebar.caption(
            "Normalized: "
            + ", ".join(
                f"{CATEGORY_LABELS[c]} {w / total:.0%}" for c, w in weights.items() if w > 0
            )
        )

    use_llm = st.sidebar.checkbox(
        "Use LLM for the narrative",
        value=settings.llm_enabled,
        disabled=not settings.llm_enabled,
        help=(
            "Requires a key at the top of this sidebar. The model only rewrites a fact sheet "
            "derived from the evidence and its output is rejected if it introduces "
            "unsupported figures. Without a key the narrative is generated deterministically."
        ),
    )

    run = st.sidebar.button("Run analysis", type="primary", width="stretch")

    request = AnalysisRequest(
        question=question,
        geographies=selected,
        category_weights=weights if total > 0 else None,
        retailer_profile=profile,
        use_llm_narrative=use_llm,
    )
    return request, run


def render_refusal(result: AnalysisResult) -> None:
    refusal = result.refusal
    assert refusal is not None

    st.error("This question cannot be answered reliably from the available evidence.")
    st.markdown(f"**Why**  \n{refusal.reason}")

    left, right = st.columns(2)
    with left:
        st.markdown("**What makes it unsupportable**")
        for entry in refusal.unsupported_because:
            st.markdown(f"- {entry}")
    with right:
        st.markdown("**What would be required to answer it**")
        for entry in refusal.required_inputs:
            st.markdown(f"- {entry}")

    st.info(f"**Offered instead**  \n{refusal.offered_alternative}")

    if refusal.supported_capabilities:
        with st.expander("What this system can do"):
            for capability in refusal.supported_capabilities:
                st.markdown(f"- {capability}")


def render_recommendation(result: AnalysisResult) -> None:
    recommendation = result.recommendation
    assert recommendation is not None
    ranked = recommendation.ranked_regions

    st.subheader("Executive recommendation")

    leader = ranked[0]
    columns = st.columns([2, 1, 1, 1])
    columns[0].metric(
        "Leading region",
        leader.geography.display_name,
        f"score {leader.overall_score:.1f}/100" if leader.overall_score is not None else "-",
    )
    if len(ranked) > 1 and ranked[1].overall_score is not None and leader.overall_score is not None:
        columns[1].metric(
            "Margin over runner-up",
            f"{leader.overall_score - ranked[1].overall_score:.1f} pts",
            ranked[1].geography.display_name,
        )
    columns[2].metric("Evidence completeness", f"{recommendation.evidence_completeness:.0%}")
    columns[3].metric("Reproducibility hash", result.reproducibility_hash or "-")

    st.caption(f"Confidence: {recommendation.confidence_label}")
    st.caption(f"Narrative generated by: {recommendation.generated_by}")

    st.markdown(recommendation.narrative)

    with st.expander(f"Caveats attached to this recommendation ({len(recommendation.caveats)})"):
        for caveat in recommendation.caveats:
            st.markdown(f"- {caveat}")


def render_dashboard(result: AnalysisResult) -> None:
    recommendation = result.recommendation
    evidence = result.evidence
    assert recommendation is not None and evidence is not None
    ranked = recommendation.ranked_regions

    st.subheader("Comparison dashboard")

    overall = pd.DataFrame(
        [
            {
                "Region": region.geography.display_name,
                "Overall score": region.overall_score,
                "Rank": region.rank,
            }
            for region in ranked
        ]
    )

    left, right = st.columns([1, 1])

    with left:
        st.markdown("**Overall score by region**")
        chart = (
            alt.Chart(overall.dropna(subset=["Overall score"]))
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("Overall score:Q", scale=alt.Scale(domain=[0, 100]), title="Score (0-100)"),
                y=alt.Y("Region:N", sort="-x", title=None),
                color=alt.Color(
                    "Overall score:Q",
                    scale=alt.Scale(scheme="blues"),
                    legend=None,
                ),
                tooltip=["Region", "Rank", alt.Tooltip("Overall score:Q", format=".2f")],
            )
            .properties(height=max(160, 46 * len(overall)))
        )
        st.altair_chart(chart, width="stretch")

    category_rows = []
    for region in ranked:
        for category_score in region.category_scores:
            category_rows.append(
                {
                    "Region": region.geography.display_name,
                    "Category": CATEGORY_LABELS[category_score.category],
                    "Score": category_score.score,
                    "Metrics used": f"{category_score.metrics_included}/{category_score.metrics_total}",
                    "Effective weight": category_score.effective_category_weight,
                }
            )
    category_frame = pd.DataFrame(category_rows)

    with right:
        st.markdown("**Category score by region**")
        scored = category_frame.dropna(subset=["Score"])
        if scored.empty:
            st.info("No category produced a score.")
        else:
            heat = (
                alt.Chart(scored)
                .mark_rect()
                .encode(
                    x=alt.X("Region:N", title=None),
                    y=alt.Y("Category:N", title=None),
                    color=alt.Color(
                        "Score:Q",
                        scale=alt.Scale(scheme="blues", domain=[0, 100]),
                        title="Score",
                    ),
                    tooltip=[
                        "Region",
                        "Category",
                        alt.Tooltip("Score:Q", format=".1f"),
                        "Metrics used",
                    ],
                )
                .properties(height=max(160, 46 * scored["Category"].nunique()))
            )
            st.altair_chart(heat, width="stretch")

    st.markdown("**Metric-level comparison**")
    st.caption(
        "Raw values as returned by Atlas. 'n/a' marks a region and metric where no usable "
        "value was available; the reason is shown in the evidence panel."
    )

    registry = load_registry()
    metric_ids = sorted({item.metric.metric_id for item in evidence.items})
    region_names = [region.geography.display_name for region in ranked]

    table_rows = []
    for metric_id in metric_ids:
        metric = registry.get(metric_id)
        if metric is None:
            continue
        row: dict[str, object] = {
            "Metric": metric.display_name,
            "Category": CATEGORY_LABELS[metric.category],
            "Unit": str(metric.unit),
            "Direction": "higher is better"
            if metric.direction.value == "higher_is_better"
            else "lower is better",
        }
        excluded = next(
            (entry for entry in evidence.excluded_metrics if entry.metric_id == metric_id), None
        )
        for region in ranked:
            item = next(
                (
                    candidate
                    for candidate in evidence.for_metric(metric_id)
                    if candidate.geography.slug == region.geography.slug
                ),
                None,
            )
            if item is None or not item.is_usable:
                row[region.geography.display_name] = "n/a"
            else:
                row[region.geography.display_name] = format_value(item.raw_value, metric.unit)
        row["Status"] = "Excluded" if excluded else "Scored"
        table_rows.append(row)

    frame = pd.DataFrame(table_rows)
    if not frame.empty:
        ordered = ["Metric", "Category", "Unit", "Direction", *region_names, "Status"]
        st.dataframe(
            frame[[column for column in ordered if column in frame.columns]],
            width="stretch",
            hide_index=True,
        )

    st.markdown("**Category detail**")
    st.caption("What each category measures, and which metrics stand behind it.")
    pivot = category_frame.pivot(index="Category", columns="Region", values="Score").round(1)
    pivot.insert(
        0,
        "What it measures",
        [
            next(
                (
                    CATEGORY_DESCRIPTIONS[category]
                    for category in MetricCategory
                    if CATEGORY_LABELS[category] == label
                ),
                "",
            )
            for label in pivot.index
        ],
    )
    st.dataframe(pivot, width="stretch")


def render_evidence(result: AnalysisResult) -> None:
    evidence = result.evidence
    assert evidence is not None

    st.subheader("Evidence panel")
    st.caption(
        f"Package {evidence.package_id} - every value below is traceable to one of the "
        f"{len(evidence.raw_calls)} recorded Atlas call(s)."
    )

    rows = []
    for item in sorted(evidence.items, key=lambda i: (i.metric.metric_id, i.geography.slug)):
        rows.append(
            {
                "Metric": item.metric.display_name,
                "Atlas datapoint": item.atlas_datapoint
                + (f"[{item.metric.atlas_item_code}]" if item.metric.atlas_item_code else ""),
                "Geography": item.geography.slug,
                "Answered for": item.reported_geography or "-",
                "Raw value": format_value(item.raw_value, item.metric.unit)
                if item.raw_value is not None
                else "-",
                "Normalized": f"{item.normalized_value:.1f}"
                if item.normalized_value is not None
                else "-",
                "Period": item.period or "-",
                "Source": item.source or "-",
                "Validation": STATUS_LABELS.get(item.validation_status, str(item.validation_status)),
                "Call id": item.call_id or "-",
                "Notes": " ".join(item.validation_notes) if item.validation_notes else "",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=420)

    if evidence.excluded_metrics:
        st.markdown("**Excluded metrics and why**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Metric": entry.display_name,
                        "Atlas datapoint": entry.atlas_datapoint,
                        "Status": STATUS_LABELS.get(entry.status, str(entry.status)),
                        "Reason": entry.reason,
                    }
                    for entry in evidence.excluded_metrics
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    st.markdown("**Raw Atlas calls**")
    for call in evidence.raw_calls:
        header = (
            f"{call.method} {call.url} - HTTP {call.status_code} - "
            f"{call.attempts} attempt(s) - {call.elapsed_seconds}s - id {call.call_id}"
        )
        with st.expander(header):
            st.caption("Credentials are stripped before a request or response is stored.")
            st.markdown("Request")
            st.json(call.request_body or {}, expanded=False)
            st.markdown("Response")
            st.json(call.response_body or {}, expanded=False)


def render_trace(result: AnalysisResult) -> None:
    st.subheader("Execution trace")
    st.caption(
        "Each step the system took, in order. The agentic layers appear in 'parse_intent' "
        "and 'select_metrics'; every number originates in 'deterministic_scoring'."
    )
    for index, entry in enumerate(result.trace, start=1):
        with st.expander(f"{index}. {entry.step} - {entry.detail}"):
            if entry.payload:
                st.json(entry.payload, expanded=False)
            else:
                st.caption("No structured payload for this step.")

    if result.weight_adjustments:
        st.markdown("**Weight renormalizations applied**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Metric": adjustment.metric_id,
                        "Category": CATEGORY_LABELS[adjustment.category],
                        "Original weight": adjustment.original_weight,
                        "Reason": adjustment.reason,
                    }
                    for adjustment in result.weight_adjustments
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    if result.evidence and result.recommendation:
        with st.expander("Final evidence package supplied to the explanation layer"):
            st.json(
                {
                    "package_id": result.evidence.package_id,
                    "reproducibility_hash": result.reproducibility_hash,
                    "usable_items": len(result.evidence.usable_items()),
                    "total_items": len(result.evidence.items),
                    "citations": result.recommendation.citations,
                },
                expanded=False,
            )


def render_limitations(result: AnalysisResult) -> None:
    st.subheader("Limitations")
    order = {
        LimitationSeverity.BLOCKING: 0,
        LimitationSeverity.CAUTION: 1,
        LimitationSeverity.INFO: 2,
    }
    for limitation in sorted(result.limitations, key=lambda l: order[l.severity]):
        if limitation.severity == LimitationSeverity.BLOCKING:
            st.error(f"**{limitation.title}**  \n{limitation.detail}")
        elif limitation.severity == LimitationSeverity.CAUTION:
            st.warning(f"**{limitation.title}**  \n{limitation.detail}")
        else:
            st.info(f"**{limitation.title}**  \n{limitation.detail}")

    st.markdown("**Additional data required for a real investment decision**")
    for requirement in [
        "Site-level rent, common-area maintenance, and build-out cost for each candidate site.",
        "Observed foot traffic or vehicle counts at the specific sites.",
        "Competitor store locations, formats, and estimated category share in each trade area.",
        "The retailer's existing store network and modelled cannibalization.",
        "Customer transaction, basket, and loyalty data.",
        "Category-level gross margin, markdown, and shrink assumptions.",
        "Distribution and supply-chain cost to serve each location.",
        "Trade-area drive-time isochrones rather than administrative boundaries.",
    ]:
        st.markdown(f"- {requirement}")


def render_assistant(settings: Settings, result: AnalysisResult | None) -> None:
    """Balloon chat that walks a business reader through the app and the current result."""
    st.subheader("Ask the assistant")
    st.caption(
        "A guide for the non-technical reader. It answers only from the evidence this "
        "analysis produced and the approved metric registry. It cannot estimate, forecast, "
        "or reach outside that, and any reply that introduces a figure the evidence does "
        "not contain is discarded before you see it."
    )

    context = build_context(
        registry=load_registry(),
        settings=settings,
        result=result,
        scope_note=DEMO_TOKEN_SCOPE_NOTE,
    )

    if "chat" not in st.session_state:
        st.session_state.chat = []

    if not settings.llm_enabled:
        st.info(
            "No OpenAI key is set, so replies are assembled deterministically from the "
            "evidence rather than written conversationally. Add a key at the top of the "
            "sidebar for a fuller conversation. The grounding rules are identical either way."
        )

    pending: str | None = None

    st.markdown("**Suggested questions**")
    columns = st.columns(len(context.suggestions))
    for column, suggestion in zip(columns, context.suggestions):
        if column.button(suggestion, width="stretch", key=f"suggest_{suggestion}"):
            pending = suggestion

    history = st.container()

    typed = st.chat_input("Ask about the regions, the score, the evidence, or how this works")
    if typed:
        pending = typed

    if pending:
        prior = [(entry["role"], entry["content"]) for entry in st.session_state.chat]
        reply = ask(pending, context, settings, history=prior)
        st.session_state.chat.append({"role": "user", "content": pending})
        st.session_state.chat.append(
            {
                "role": "assistant",
                "content": reply.text,
                "generated_by": reply.generated_by,
                "refused": reply.refused,
                "notes": reply.notes,
            }
        )

    with history:
        if not st.session_state.chat:
            with st.chat_message("assistant"):
                st.markdown(
                    "I can walk you through this. Ask me why a region ranks where it does, "
                    "where any number came from, what was left out, or what this analysis "
                    "cannot tell you.\n\nIf you ask me something the evidence does not "
                    "support, I will say so rather than guess."
                )
        for entry in st.session_state.chat:
            with st.chat_message(entry["role"]):
                st.markdown(entry["content"])
                if entry["role"] == "assistant":
                    if entry.get("refused"):
                        st.caption("Refused deterministically; the model was not called.")
                    for note in entry.get("notes") or []:
                        st.warning(note)
                    st.caption(f"Answered by: {entry.get('generated_by', 'deterministic')}")

    if st.session_state.chat and st.button("Clear conversation"):
        st.session_state.chat = []
        st.rerun()


def render_registry() -> None:
    registry = load_registry()
    st.subheader("Approved metric registry")
    st.caption(
        f"{len(registry)} metrics. Each names an Atlas datapoint that was confirmed to return "
        "a value during verification. A datapoint with no verification record cannot be loaded."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Metric": metric.display_name,
                    "Atlas datapoint": metric.atlas_datapoint
                    + (f"[{metric.atlas_item_code}]" if metric.atlas_item_code else ""),
                    "Category": CATEGORY_LABELS[metric.category],
                    "Unit": str(metric.unit),
                    "Direction": str(metric.direction),
                    "Weight in category": metric.weight,
                    "Source": metric.source,
                    "Levels": ", ".join(str(t) for t in metric.supported_geography_types),
                    "Why it matters to a retailer": metric.retail_rationale,
                }
                for metric in registry.all()
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def main() -> None:
    st.title("Retail Location Intelligence")
    st.caption(
        "Evidence-bound region comparison for retail site selection, built on the StateBook "
        "Atlas API. Illustrative scenario only: this prototype uses no proprietary retailer "
        "data and is not affiliated with any retailer."
    )

    try:
        load_registry()
    except UnverifiedMetricError as exc:
        st.error(str(exc))
        st.stop()

    settings = assistant_settings()
    request, run = sidebar(settings)

    if "result" not in st.session_state:
        st.session_state.result = None

    if run:
        if len(request.geographies) < 2:
            st.warning("Select at least two candidate regions.")
        else:
            with st.spinner("Planning, calling Atlas, validating, and scoring..."):
                st.session_state.result = AnalysisPipeline(settings=settings).run(request)

    result: AnalysisResult | None = st.session_state.result

    if result is None:
        tabs = st.tabs(["Assistant", "Metric registry"])
        with tabs[0]:
            st.info(
                "Choose candidate regions in the sidebar and select **Run analysis**. "
                "In the meantime, the assistant can explain what this tool does and how "
                "it decides what it is allowed to say."
            )
            render_assistant(settings, None)
        with tabs[1]:
            render_registry()
        return

    if result.refused:
        tabs = st.tabs(["Recommendation", "Assistant", "Trace", "Limitations", "Metric registry"])
        with tabs[0]:
            render_refusal(result)
            if result.evidence is not None:
                st.divider()
                st.caption(
                    "The underlying evidence is still shown because it was retrieved and "
                    "validated; only the ranking is withheld."
                )
                render_evidence(result)
        with tabs[1]:
            render_assistant(settings, result)
        with tabs[2]:
            render_trace(result)
        with tabs[3]:
            render_limitations(result)
        with tabs[4]:
            render_registry()
        return

    tabs = st.tabs(
        [
            "Recommendation",
            "Assistant",
            "Comparison dashboard",
            "Evidence",
            "Trace",
            "Limitations",
            "Metric registry",
        ]
    )
    with tabs[0]:
        render_recommendation(result)
    with tabs[1]:
        render_assistant(settings, result)
    with tabs[2]:
        render_dashboard(result)
    with tabs[3]:
        render_evidence(result)
    with tabs[4]:
        render_trace(result)
    with tabs[5]:
        render_limitations(result)
    with tabs[6]:
        render_registry()

    st.divider()
    st.download_button(
        "Download full result as JSON",
        data=json.dumps(result.model_dump(mode="json"), indent=2, default=str),
        file_name=f"rli_result_{result.reproducibility_hash or 'result'}.json",
        mime="application/json",
    )


if __name__ == "__main__":
    main()
