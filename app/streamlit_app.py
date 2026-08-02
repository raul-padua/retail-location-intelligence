"""Retail Location Intelligence - founder demo UI.

The interface walks an executive through a decision rather than a form: describe the
objective, answer anything material the planner could not infer, review the proposed
analysis, approve it, and only then see a result. Every stage transition is owned by
:mod:`app.workflow`; this module renders whichever stage it is handed and disables the
controls the state says are unavailable.

Nothing here computes. The panels display what the deterministic services produced, and
where a control looks like it changes an answer - a weight slider, a revision - it changes
a *plan*, which has to pass validation and approval before it can change anything else.
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
from app import workflow
from app.workflow import Stage, WorkflowError, WorkflowState
from core.config import DEFAULT_LLM_MODEL, Settings, get_settings
from explanation.assistant import ask, build_context
from metrics.registry import UnverifiedMetricError, get_registry
from models.analysis import AUTHORITY_LABELS, AnalysisResult, LimitationSeverity
from models.evidence import ValidationStatus
from models.metrics import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_LABELS,
    CATEGORY_WEIGHT_GUIDANCE,
    MetricCategory,
    Unit,
)
from models.plan import AnalysisPlanProposal
from orchestration.pipeline import AnalysisPipeline
from planning.capabilities import get_capability_registry
from scoring.sensitivity import STRATEGY_PROFILES, build_sensitivity_report

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

# Written the way an executive would say it, because the point of the planner is that it
# reads this rather than a settings panel.
OBJECTIVE_EXAMPLES: dict[str, str] = {
    "Suburban family store, growth-led": (
        "We are evaluating Burlington, South Burlington, and Winooski for a suburban "
        "apparel store targeting middle-income families. Prioritize growth and "
        "accessibility over current market size."
    ),
    "Campus-oriented banner": (
        "Looking for a campus-oriented apparel banner site. Students and young adults "
        "matter most, and we care about accessibility on foot."
    ),
    "Purchasing power screen": (
        "Screen these markets for a premium apparel store. Purchasing power is the "
        "priority; growth matters less than what households can spend today."
    ),
    "Deliberately vague": "Where should we put our next store?",
    "Asks for data we do not have": (
        "Prioritize low rent, high foot traffic, and limited competition nearby."
    ),
    "Asks for a forecast": (
        "Which of these locations will generate the highest five-year ROI?"
    ),
}

STAGE_STEPS: list[tuple[Stage, str]] = [
    (Stage.DESCRIBE, "Describe the decision"),
    (Stage.CLARIFY, "Clarify"),
    (Stage.REVIEW, "Review and approve"),
    (Stage.EXECUTED, "Result"),
]

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


def sidebar(settings: Settings, state: WorkflowState) -> bool:
    """Environment status, planner mode, and where the user currently is."""
    st.sidebar.title("Session")

    if settings.atlas_token:
        st.sidebar.success(
            f"Atlas token configured{' (public demo token)' if settings.is_demo_token else ''}"
        )
    else:
        st.sidebar.error("STATEBOOK_API_TOKEN is not set. Copy .env.example to .env.")

    st.sidebar.caption(DEMO_TOKEN_SCOPE_NOTE)

    st.sidebar.subheader("Where you are")
    reached = [stage for stage, _ in STAGE_STEPS]
    position = reached.index(state.stage) if state.stage in reached else -1
    for index, (stage, label) in enumerate(STAGE_STEPS):
        if state.stage == Stage.REFUSED:
            marker = "-"
        elif index < position:
            marker = "done"
        elif index == position:
            marker = "**now**"
        else:
            marker = "-"
        st.sidebar.markdown(f"{index + 1}. {label} - {marker}")
    if state.stage == Stage.REFUSED:
        st.sidebar.error("Request refused before planning.")

    st.sidebar.subheader("Planner")
    use_llm = st.sidebar.checkbox(
        "Use the language model to interpret the objective",
        value=settings.llm_enabled,
        disabled=not settings.llm_enabled,
        help=(
            "With a key, the model reads the objective and proposes a plan; every field it "
            "returns is revalidated against the registry and the geography allowlist before "
            "you see it. Without a key, a deterministic planner produces the same shape from "
            "pattern matching. Neither can produce a value or a ranking."
        ),
        key="use_llm_planner",
    )
    st.sidebar.caption(
        "Planner: "
        + ("language model, revalidated" if use_llm and settings.llm_enabled else "deterministic")
    )

    if state.stage != Stage.DESCRIBE and st.sidebar.button("Start a new analysis", width="stretch"):
        st.session_state.workflow = workflow.reset(state)
        st.session_state.chat = []
        st.rerun()

    return use_llm and settings.llm_enabled


def render_describe(state: WorkflowState, settings: Settings, use_llm: bool) -> None:
    """Step 1. A business objective in the user's words, plus the candidate set."""
    st.subheader("Describe the decision")
    st.caption(
        "Write the objective the way you would brief a colleague. The planner reads it, "
        "says what it inferred, asks about anything material it could not, and proposes an "
        "analysis for you to approve. It does not answer the question at this stage."
    )

    example = st.selectbox(
        "Start from an example",
        ["Write my own", *OBJECTIVE_EXAMPLES],
        help="These cover the interesting cases, including the ones the system refuses.",
    )
    default = OBJECTIVE_EXAMPLES.get(example, state.objective)

    objective = st.text_area(
        "Business objective",
        value=default,
        height=120,
        placeholder=(
            "e.g. We are evaluating Burlington and South Burlington for a suburban apparel "
            "store targeting middle-income families. Prioritize growth over current size."
        ),
    )

    choices = demo_geography_choices()
    labels = {geography.slug: geography.display_name for geography in choices}
    preset = st.selectbox("Preset candidate set", list(PRESETS), index=0)
    selected = st.multiselect(
        "Candidate regions",
        options=list(labels),
        default=state.geographies or PRESETS[preset],
        format_func=lambda slug: labels.get(slug, slug),
        help=(
            "Only regions licensed by the active token appear here. Naming a region in the "
            "objective does not add it: the allowlist is the only route in."
        ),
    )

    with st.expander("Optional retailer profile (the planner will infer what you leave blank)"):
        columns = st.columns(3)
        retailer_type = columns[0].text_input(
            "Retailer type", placeholder="e.g. national mainstream apparel"
        )
        store_format = columns[1].text_input(
            "Store format", placeholder="e.g. suburban full-price"
        )
        target_segments = columns[2].text_input(
            "Target customers", placeholder="e.g. middle-income families"
        )

    if st.button("Interpret and propose a plan", type="primary", width="stretch"):
        if not objective.strip():
            st.warning("Describe the decision first.")
            return
        with st.spinner("Interpreting the objective and constructing a plan proposal..."):
            st.session_state.workflow = workflow.describe(
                state,
                objective,
                selected,
                retailer_type=retailer_type or None,
                store_format=store_format or None,
                target_segments=target_segments or None,
                settings=settings,
                use_llm=use_llm,
            )
        st.rerun()

    st.divider()
    st.caption(
        "Nothing is sent to StateBook Atlas at this stage. Planning reads the objective, "
        "the approved metric registry, and the capability registry, and produces a proposal."
    )


def render_clarify(state: WorkflowState, settings: Settings, use_llm: bool) -> None:
    """Step 2. Only material questions, and never more than three."""
    plan = state.plan
    assert plan is not None

    st.subheader("A few things would change the analysis")
    st.caption(
        "These are asked because the answer changes which metrics are used or how they are "
        "weighted, not to fill in a form. Anything left blank proceeds on a stated "
        "assumption, which you will see on the next screen."
    )

    answers: dict[str, str] = {}
    for question in plan.clarification_questions[:3]:
        with st.container(border=True):
            st.markdown(
                f"**{question.question}**"
                + ("  \n:red[Required]" if question.required else "  \nOptional")
            )
            st.caption(f"Why it matters: {question.why_it_matters}")
            if question.affects:
                st.caption("Could change: " + ", ".join(question.affects))
            answers[question.question_id] = st.text_input(
                "Your answer",
                value=question.answer or "",
                key=f"answer_{question.question_id}",
                placeholder=question.safe_default or "",
                label_visibility="collapsed",
            )
            if question.safe_default:
                st.caption(f"If you skip this: {question.safe_default}")

    required_open = [q.question_id for q in plan.unanswered_required_questions]
    unanswered_required = [
        qid for qid in required_open if not (answers.get(qid) or "").strip()
    ]

    columns = st.columns([1, 1, 2])
    if columns[0].button("Submit answers", type="primary", width="stretch"):
        if unanswered_required:
            st.error("The required question above has to be answered before the plan can run.")
        else:
            st.session_state.workflow = workflow.answer(
                state, answers, settings=settings, use_llm=use_llm
            )
            st.rerun()

    if columns[1].button(
        "Continue without answering",
        width="stretch",
        disabled=bool(required_open),
        help=(
            "Available only when every open question is optional. The assumptions used "
            "instead are shown on the review screen."
        ),
    ):
        st.session_state.workflow = workflow.answer(
            state, {}, settings=settings, use_llm=use_llm
        )
        st.rerun()

    if columns[2].button("Change the objective", width="stretch"):
        st.session_state.workflow = workflow.reject(state, note="returned to the objective")
        st.rerun()


def render_plan(plan: AnalysisPlanProposal, *, compact: bool = False) -> None:
    """The proposal itself. Used on the review screen and again after execution."""
    registry = load_registry()

    header = st.columns(4)
    header[0].metric("Plan", f"{plan.plan_id[-6:]} v{plan.version}")
    header[1].metric("Status", str(plan.status).replace("_", " ").title())
    header[2].metric("Regions", len(plan.candidate_geographies))
    header[3].metric("Metrics", len(plan.selected_metric_ids))

    st.caption(f"Proposed by: {plan.planner_provenance.describe()}")
    if plan.planner_rationale:
        st.markdown(plan.planner_rationale)

    profile = plan.retail_strategy_profile
    st.markdown("**Interpreted retailer profile**")
    rows = []
    for name, attributed in profile._attributed_fields().items():
        rows.append(
            {
                "Field": name.replace("_", " ").capitalize(),
                "Value": attributed.describe() if attributed.is_known else "Not established",
                "Where it came from": str(attributed.provenance).replace("_", " "),
                "Note": attributed.note or "",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    left, right = st.columns([1, 1])

    with left:
        st.markdown("**Proposed category weights**")
        weights = pd.DataFrame(
            [
                {
                    "Category": CATEGORY_LABELS[category],
                    "Weight": weight,
                    "What it measures": CATEGORY_DESCRIPTIONS[category],
                }
                for category, weight in plan.category_weights.items()
            ]
        )
        chart = (
            alt.Chart(weights)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("Weight:Q", axis=alt.Axis(format="%"), title="Share of the score"),
                y=alt.Y("Category:N", sort="-x", title=None),
                tooltip=["Category", alt.Tooltip("Weight:Q", format=".1%"), "What it measures"],
            )
            .properties(height=max(150, 40 * len(weights)))
        )
        st.altair_chart(chart, width="stretch")

    with right:
        st.markdown("**Regions to be compared**")
        for geography in plan.candidate_geographies:
            st.markdown(f"- {geography.display_name}")
        st.markdown("**Expected output**")
        for expectation in plan.expected_outputs:
            st.markdown(f"- {expectation}")

    if not compact:
        st.markdown("**Selected metrics**")
        metric_rows = []
        for metric_id in plan.selected_metric_ids:
            metric = registry.get(metric_id)
            if metric is None:
                continue
            metric_rows.append(
                {
                    "Metric": metric.display_name,
                    "Category": CATEGORY_LABELS[metric.category],
                    "Direction": "higher is better"
                    if metric.direction.value == "higher_is_better"
                    else "lower is better",
                    "Why it matters to a retailer": metric.retail_rationale,
                }
            )
        st.dataframe(pd.DataFrame(metric_rows), width="stretch", hide_index=True, height=320)
        st.caption(
            "Atlas datapoint identifiers are deliberately absent from the plan. The registry "
            "resolves a metric id to a datapoint at execution time, after approval."
        )

    if plan.assumptions:
        st.markdown("**Assumptions the planner made**")
        for assumption in plan.assumptions:
            with st.container(border=True):
                st.markdown(f"**{assumption.subject}** - {assumption.assumption}")
                st.caption(f"Basis: {assumption.basis}")
                if assumption.reversible_by:
                    st.caption(f"To overrule: {assumption.reversible_by}")

    if plan.unsupported_requirements:
        st.markdown("**Requested, but not available**")
        for requirement in plan.unsupported_requirements:
            st.warning(
                f"**{requirement.requirement}**  \n{requirement.why_unavailable}  \n"
                f"Would require: {requirement.would_require}"
            )

    answered = [q for q in plan.clarification_questions if q.answered]
    if answered:
        st.markdown("**Clarifications you answered**")
        for question in answered:
            st.markdown(f"- {question.question} - *{question.answer}*")

    if plan.validation.disclosures:
        st.markdown("**Adjustments the validator made**")
        for disclosure in plan.validation.disclosures:
            st.info(disclosure)

    if plan.validation.warnings:
        for warning in plan.validation.warnings:
            st.caption(warning)

    rejected = plan.planner_provenance.rejected_fields
    if rejected:
        with st.expander(f"Planner output rejected by validation ({len(rejected)})"):
            st.caption(
                "The model returned these and they did not survive revalidation. They are "
                "shown because a silent rejection is indistinguishable from a model that "
                "never misbehaves."
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Field": entry.field, "Value": entry.offending_value, "Reason": entry.reason}
                        for entry in rejected
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    st.markdown("**What this analysis will not be able to conclude**")
    for limit in [
        "Which location will perform best commercially. Atlas describes markets, not stores.",
        "Any causal claim. A market indicator is a correlate of opportunity, not a driver "
        "of sales.",
        "Anything about rent, foot traffic, competitors, or your existing network.",
    ]:
        st.markdown(f"- {limit}")


def render_review(state: WorkflowState, settings: Settings, use_llm: bool) -> None:
    """Steps 3 and 4. Review, edit, then approve or reject."""
    plan = state.plan
    assert plan is not None

    st.subheader("Review the proposed analysis")
    st.caption(
        "Nothing has been retrieved or calculated. This is the agent's proposal, and it "
        "runs only if you approve it."
    )

    if not plan.validation.passed:
        st.error("This plan did not pass deterministic validation and cannot be approved.")
        for check in plan.validation.failures:
            st.markdown(f"- **{check.name}**: {check.detail}")

    render_plan(plan)

    st.divider()
    st.markdown("### Approve, edit, or reject")

    with st.expander("Edit the plan before approving"):
        st.caption(
            "Edits are recorded against the plan and revalidated. The trace distinguishes "
            "what the planner proposed from what you changed."
        )

        registry = load_registry()
        weights: dict[MetricCategory, float] = {}
        for category in MetricCategory:
            members = [
                metric.display_name
                for metric in registry.by_category(category)
                if metric.metric_id in plan.selected_metric_ids
            ]
            weights[category] = st.slider(
                CATEGORY_LABELS[category],
                0.0,
                1.0,
                float(plan.category_weights.get(category, 0.0)),
                0.01,
                key=f"edit_weight_{category}",
                help=(
                    f"**{CATEGORY_DESCRIPTIONS[category]}**\n\n"
                    f"{CATEGORY_WEIGHT_GUIDANCE[category]}\n\n"
                    "Measured by: " + (", ".join(members) if members else "nothing in this plan")
                ),
            )

        chosen_metrics = st.multiselect(
            "Metrics in the analysis",
            options=[metric.metric_id for metric in registry.all()],
            default=plan.selected_metric_ids,
            format_func=lambda metric_id: (
                registry.get(metric_id).display_name if registry.get(metric_id) else metric_id
            ),
            help="Only metrics verified against Atlas can be selected.",
        )

        labels = {g.slug: g.display_name for g in demo_geography_choices()}
        chosen_regions = st.multiselect(
            "Candidate regions",
            options=list(labels),
            default=[geography.slug for geography in plan.candidate_geographies],
            format_func=lambda slug: labels.get(slug, slug),
        )

        if st.button("Apply edits and revalidate", width="stretch"):
            try:
                st.session_state.workflow = workflow.edit(
                    state,
                    category_weights=weights,
                    selected_metric_ids=chosen_metrics,
                    geographies=chosen_regions,
                )
            except WorkflowError as exc:
                st.error(str(exc))
            else:
                st.rerun()

    columns = st.columns([2, 1, 1])

    approve_disabled = not state.can_approve
    if columns[0].button(
        "Approve and run the analysis",
        type="primary",
        width="stretch",
        disabled=approve_disabled,
        help=(
            "Approval is the only route to an Atlas call. It is unavailable until the plan "
            "passes deterministic validation."
        ),
    ):
        with st.spinner("Calling Atlas, validating, scoring..."):
            try:
                st.session_state.workflow = workflow.approve_and_run(
                    state,
                    AnalysisPipeline(settings=settings),
                    use_llm_narrative=use_llm,
                )
            except WorkflowError as exc:
                st.error(str(exc))
            else:
                st.rerun()

    if columns[1].button("Back to questions", width="stretch", disabled=not plan.clarification_questions):
        st.session_state.workflow = replace_stage(state, Stage.CLARIFY)
        st.rerun()

    if columns[2].button("Reject and start over", width="stretch"):
        st.session_state.workflow = workflow.reject(state, note="rejected at review")
        st.rerun()

    if approve_disabled:
        st.caption("Approval is disabled until the plan passes validation.")


def replace_stage(state: WorkflowState, stage: Stage) -> WorkflowState:
    """Move back to an earlier stage without touching the plan."""
    from dataclasses import replace as _replace

    return _replace(state, stage=stage)


def render_planning_refusal(state: WorkflowState) -> None:
    refusal = state.refusal
    assert refusal is not None

    st.error("This request cannot be turned into an analysis.")
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

    st.caption(
        "This was refused before any planner ran and before any Atlas call was constructed. "
        "The attempt is recorded in the trace below."
    )
    render_planning_trace(state)

    if st.button("Describe a different decision", type="primary"):
        st.session_state.workflow = workflow.reset(state)
        st.rerun()


def render_planning_trace(state: WorkflowState) -> None:
    if not state.planning_trace:
        return
    with st.expander(f"Planning trace ({len(state.planning_trace)} steps)"):
        for index, entry in enumerate(state.planning_trace, start=1):
            st.markdown(
                f"**{index}. {entry.step}** - {AUTHORITY_LABELS[entry.authority]}  \n"
                f"{entry.detail}"
            )
            if entry.payload:
                st.json(entry.payload, expanded=False)


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
    st.subheader("Agent decision log")
    st.caption(
        "Every step, in order, labelled with what authorized it. The question this is "
        "designed to answer is not 'what happened' but 'who or what decided this' - a "
        "figure carrying API or calculation authority came from evidence, while one "
        "carrying agent authority is a proposal that had to survive validation."
    )

    authorities = sorted({entry.authority for entry in result.trace}, key=str)
    chosen = st.multiselect(
        "Filter by authority",
        options=authorities,
        default=authorities,
        format_func=lambda authority: AUTHORITY_LABELS[authority],
        key="trace_authority_filter",
    )

    counts = pd.DataFrame(
        [
            {
                "Authority": AUTHORITY_LABELS[authority],
                "Steps": len(result.trace_by_authority(authority)),
            }
            for authority in authorities
        ]
    )
    st.dataframe(counts, width="stretch", hide_index=True)

    for index, entry in enumerate(result.trace, start=1):
        if entry.authority not in chosen:
            continue
        with st.expander(
            f"{index}. {entry.step} - [{AUTHORITY_LABELS[entry.authority]}] {entry.detail}"
        ):
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


@st.cache_data(show_spinner=False)
def _sensitivity(package_id: str, _result: AnalysisResult):
    """Cached on the evidence package, since the inputs are fixed once a run completes."""
    evidence = _result.evidence
    plan = _result.plan
    assert evidence is not None and plan is not None
    # Taken from the evidence rather than the registry so that any metric-weight override
    # the approved plan carried is the one re-scored here.
    metrics = {item.metric.metric_id: item.metric for item in evidence.items}
    return build_sensitivity_report(evidence, metrics, dict(plan.category_weights))


def render_sensitivity(result: AnalysisResult) -> None:
    """Is the recommendation a fact about the market, or a fact about the weights?"""
    st.subheader("Strategy lenses and sensitivity")
    st.caption(
        "The same Atlas values, re-scored under different documented weightings. None of "
        "these is the correct model. The useful question is whether the answer survives "
        "the disagreement between them - and all of this is calculated deterministically, "
        "never estimated by a model."
    )

    if result.evidence is None or result.plan is None:
        st.info("No evidence package to analyse.")
        return

    report = _sensitivity(result.evidence.package_id, result)
    comparison = report.comparison

    if comparison.stable:
        st.success(f"**Stable.** {comparison.stability_note}")
    else:
        st.warning(f"**Assumption-sensitive.** {comparison.stability_note}")

    with st.expander("What each lens weights, and when you would use it"):
        for profile in STRATEGY_PROFILES:
            st.markdown(f"**{profile.display_name}** - {profile.description}")
            st.caption(f"When to use it: {profile.when_to_use}")
            st.caption(
                ", ".join(
                    f"{CATEGORY_LABELS[category]} {weight:.0%}"
                    for category, weight in profile.category_weights.items()
                )
            )

    rows = []
    for ranking in [comparison.baseline, *comparison.profiles]:
        for region in ranking.regions:
            rows.append(
                {
                    "Lens": ranking.display_name,
                    "Region": region.display_name,
                    "Rank": region.rank,
                    "Score": region.overall_score,
                    "Hash": ranking.reproducibility_hash,
                }
            )
    frame = pd.DataFrame(rows)

    left, right = st.columns([3, 2])

    with left:
        st.markdown("**Rank under each lens**")
        scored = frame.dropna(subset=["Score"])
        if not scored.empty:
            chart = (
                alt.Chart(scored)
                .mark_circle(size=260, opacity=0.85)
                .encode(
                    x=alt.X("Lens:N", title=None, axis=alt.Axis(labelAngle=-20)),
                    y=alt.Y(
                        "Rank:Q",
                        scale=alt.Scale(reverse=True, domain=[scored["Rank"].max() + 0.5, 0.5]),
                        title="Rank (1 is best)",
                    ),
                    color=alt.Color("Region:N", title="Region"),
                    tooltip=["Lens", "Region", "Rank", alt.Tooltip("Score:Q", format=".2f")],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, width="stretch")

    with right:
        st.markdown("**Winner under each lens**")
        for profile_id, winner in comparison.winners.items():
            st.markdown(f"- {profile_id.replace('-', ' ').title()}: **{winner}**")
        st.markdown("**Reproducibility hashes**")
        st.dataframe(
            frame[["Lens", "Hash"]].drop_duplicates(),
            width="stretch",
            hide_index=True,
        )

    st.markdown("**Score and rank movement against your approved weights**")
    delta_rows = []
    for profile_id, deltas in comparison.deltas.items():
        for delta in deltas:
            delta_rows.append(
                {
                    "Lens": profile_id.replace("-", " ").title(),
                    "Region": delta.display_name,
                    "Rank under your weights": delta.baseline_rank,
                    "Rank under this lens": delta.comparison_rank,
                    "Rank change": delta.rank_change,
                    "Score change": delta.score_change,
                }
            )
    if delta_rows:
        st.dataframe(pd.DataFrame(delta_rows), width="stretch", hide_index=True)

    st.markdown("**What is driving each region's score**")
    st.caption(
        "Each metric's contribution in points of the 0-100 overall score, under your "
        "approved weights."
    )
    influence_rows = [
        {
            "Region": entry.display_name,
            "Metric": entry.metric_name,
            "Category": CATEGORY_LABELS[entry.category],
            "Normalized": round(entry.normalized_value, 1),
            "Points contributed": round(entry.contribution, 2),
            "Share of score": entry.share_of_score,
        }
        for entry in report.influences
    ]
    if influence_rows:
        influences = pd.DataFrame(influence_rows)
        region = st.selectbox(
            "Region", sorted(influences["Region"].unique()), key="influence_region"
        )
        subset = influences[influences["Region"] == region].sort_values(
            "Points contributed", ascending=False
        )
        chart = (
            alt.Chart(subset)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("Points contributed:Q", title="Points of the overall score"),
                y=alt.Y("Metric:N", sort="-x", title=None),
                color=alt.Color("Category:N", legend=alt.Legend(title="Category")),
                tooltip=["Metric", "Category", "Normalized", "Points contributed"],
            )
            .properties(height=max(200, 26 * len(subset)))
        )
        st.altair_chart(chart, width="stretch")

    st.markdown("**What it would take to reverse the top two**")
    st.caption(
        "A deterministic scan over one category weight at a time, holding the others in "
        "proportion. A category that cannot flip the result at any weight is a category "
        "the recommendation does not hinge on."
    )
    if report.flip_points:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Category": CATEGORY_LABELS[point.category],
                        "Current weight": f"{point.current_weight:.0%}",
                        "Can flip the top two": "yes" if point.flips else "no",
                        "Weight required": f"{point.required_weight:.0%}"
                        if point.required_weight is not None
                        else "-",
                        "Direction": point.direction or "-",
                        "Note": point.note,
                    }
                    for point in report.flip_points
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Not enough scored regions to run a flip-point scan.")


def render_versions(state: WorkflowState) -> None:
    """Two executed versions side by side, and what moved between them."""
    st.subheader("Analysis versions")

    if state.previous is None or state.current is None:
        st.info(
            "Only one version has run. Ask the assistant to change something - a weight, a "
            "metric, the candidate set - and confirm the revision to produce a second one."
        )
        st.markdown("**Current version**")
        if state.current:
            render_plan(state.current.plan, compact=True)
        return

    plan_diff = state.plan_diff()
    result_diff = state.result_diff()
    assert plan_diff is not None and result_diff is not None

    if plan_diff.revision_summary:
        st.caption(f"Requested change: {plan_diff.revision_summary}")

    columns = st.columns(2)
    columns[0].metric(
        f"v{plan_diff.from_version} leader",
        result_diff.previous_leader or "-",
        result_diff.previous_hash or "",
    )
    columns[1].metric(
        f"v{plan_diff.to_version} leader",
        result_diff.new_leader or "-",
        result_diff.new_hash or "",
    )

    if result_diff.leader_changed:
        st.warning(
            "The leading region changed between versions. The evidence did not change; the "
            "weighting did."
            if not result_diff.evidence_changed
            else "The leading region changed, and so did the evidence going into the score."
        )
    else:
        st.success("The leading region held across both versions.")

    st.markdown("**What changed in the plan**")
    if plan_diff.weight_changes:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Category": CATEGORY_LABELS[change.category],
                        f"v{plan_diff.from_version}": f"{change.before:.0%}",
                        f"v{plan_diff.to_version}": f"{change.after:.0%}",
                        "Change": f"{change.after - change.before:+.0%}",
                    }
                    for change in plan_diff.weight_changes
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    for label, entries in (
        ("Metrics added", plan_diff.metrics_added),
        ("Metrics removed", plan_diff.metrics_removed),
        ("Regions added", plan_diff.regions_added),
        ("Regions removed", plan_diff.regions_removed),
        ("Assumptions added", plan_diff.assumptions_added),
        ("Assumptions removed", plan_diff.assumptions_removed),
    ):
        if entries:
            st.markdown(f"- **{label}**: {', '.join(entries)}")

    st.markdown("**What changed in the answer**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Region": delta.display_name,
                    f"Rank v{plan_diff.from_version}": delta.baseline_rank,
                    f"Rank v{plan_diff.to_version}": delta.comparison_rank,
                    "Rank change": delta.rank_change,
                    f"Score v{plan_diff.from_version}": delta.baseline_score,
                    f"Score v{plan_diff.to_version}": delta.comparison_score,
                    "Score change": delta.score_change,
                }
                for delta in result_diff.deltas
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    st.markdown("**Which deterministic inputs account for the difference**")
    for entry in result_diff.attribution:
        st.markdown(f"- {entry}")

    with st.expander(f"Full plan, v{plan_diff.from_version}"):
        render_plan(state.previous.plan, compact=True)
    with st.expander(f"Full plan, v{plan_diff.to_version}"):
        render_plan(state.current.plan, compact=True)


def render_capabilities() -> None:
    """What the agent may ask for, and what it may only recommend as a next step."""
    registry = get_capability_registry()

    st.subheader("Governed capability registry")
    st.caption(
        "The agent orchestrates from this list and nothing else. Capabilities marked "
        "unavailable are real product gaps with a named integration path; the agent may "
        "recommend one as a next step, but it can never behave as though it ran."
    )

    st.markdown("**Available now**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Capability": capability.display_name,
                    "Kind": str(capability.kind).replace("_", " "),
                    "What it does": capability.description,
                    "Deterministic": "yes" if capability.deterministic else "no",
                }
                for capability in registry.available()
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    st.markdown("**Not available**")
    for capability in registry.unavailable():
        with st.container(border=True):
            st.markdown(f"**{capability.display_name}** - {capability.description}")
            st.caption(f"Why it cannot run today: {capability.unavailable_because}")
            st.caption("Would require: " + ", ".join(capability.required_data))
            if capability.expected_provider:
                st.caption(f"Expected source: {capability.expected_provider}")


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


def render_revision_card(state: WorkflowState, settings: Settings, use_llm: bool) -> None:
    """The confirmation gate. A parked revision sits here until the user acts on it."""
    revision = state.pending_revision
    if revision is None:
        return

    with st.container(border=True):
        st.markdown("### Proposed change to the analysis")
        st.caption(
            f"Revision {revision.revision_id}, against plan v{revision.parent_version}. "
            "Nothing has run."
        )
        st.markdown(f"**Requested**  \n{revision.requested_change}")
        st.markdown(f"**Read as**  \n{revision.rationale}")

        for field_name in revision.changed_fields:
            before = revision.before_values.get(field_name)
            after = revision.proposed_values.get(field_name)
            if field_name == "category_weights":
                rows = [
                    {
                        "Category": CATEGORY_LABELS[MetricCategory(key)],
                        "Now": f"{float(before[key]):.0%}",
                        "Proposed": f"{float(value):.0%}",
                        "Change": f"{float(value) - float(before[key]):+.0%}",
                    }
                    for key, value in (after or {}).items()
                    if abs(float(value) - float((before or {}).get(key, 0.0))) > 1e-9
                ]
                if rows:
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            elif field_name == "selected_metric_ids":
                removed = sorted(set(before or []) - set(after or []))
                added = sorted(set(after or []) - set(before or []))
                if removed:
                    st.markdown(f"- Metrics removed: {', '.join(removed)}")
                if added:
                    st.markdown(f"- Metrics added: {', '.join(added)}")
            elif field_name == "candidate_geographies":
                st.markdown(f"- Regions now: {', '.join(before or [])}")
                st.markdown(f"- Regions proposed: {', '.join(after or [])}")

        st.info(f"**Likely effect**  \n{revision.expected_effect}")

        for part in revision.unsupported_parts:
            st.warning(part)

        if not revision.validation.passed:
            st.error("This revision would not pass deterministic validation.")
            for check in revision.validation.failures:
                st.markdown(f"- {check.detail}")

        columns = st.columns([1, 1, 2])
        if columns[0].button(
            "Confirm and rerun",
            type="primary",
            width="stretch",
            disabled=not revision.is_actionable,
        ):
            with st.spinner("Creating a new plan version and rerunning..."):
                try:
                    st.session_state.workflow = workflow.confirm_revision(
                        state, AnalysisPipeline(settings=settings), use_llm_narrative=use_llm
                    )
                except WorkflowError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

        if columns[1].button("Discard", width="stretch"):
            st.session_state.workflow = workflow.discard_revision(state)
            st.rerun()

        columns[2].caption(
            "Confirming creates a new plan version. The current result is kept and the two "
            "are compared on the Versions tab."
        )


def render_assistant(state: WorkflowState, settings: Settings, use_llm: bool) -> None:
    """Balloon chat that explains the current result and proposes changes to it."""
    result = state.result

    st.subheader("Ask the assistant")
    st.caption(
        "A guide for the non-technical reader. It answers only from the evidence this "
        "analysis produced and the approved metric registry. Ask it to change something - "
        "a weight, a metric, the candidate set - and it writes a proposal for you to "
        "confirm rather than acting on it."
    )

    render_revision_card(state, settings, use_llm)

    context = build_context(
        registry=load_registry(),
        settings=settings,
        result=result,
        scope_note=DEMO_TOKEN_SCOPE_NOTE,
        plan=state.plan if state.stage == Stage.EXECUTED else None,
    )

    if "chat" not in st.session_state:
        st.session_state.chat = []

    if not settings.llm_enabled:
        st.info(
            "No OpenAI key is set, so replies are assembled deterministically from the "
            "evidence rather than written conversationally. Add a key at the top of the "
            "sidebar for a fuller conversation. The grounding rules, and the revision "
            "proposals, are identical either way."
        )

    pending: str | None = None

    suggestions = list(context.suggestions)
    if state.stage == Stage.EXECUTED:
        suggestions = [*suggestions[:3], "Double the importance of household income"]

    st.markdown("**Suggested questions**")
    columns = st.columns(len(suggestions))
    for column, suggestion in zip(columns, suggestions):
        if column.button(suggestion, width="stretch", key=f"suggest_{suggestion}"):
            pending = suggestion

    history = st.container()

    typed = st.chat_input(
        "Ask about the regions, the evidence, or ask to change the analysis"
    )
    if typed:
        pending = typed

    if pending:
        prior = [(entry["role"], entry["content"]) for entry in st.session_state.chat]
        reply = ask(
            pending,
            context,
            settings,
            history=prior,
            plan=state.plan if state.stage == Stage.EXECUTED else None,
        )
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
        if reply.revision is not None and reply.revision.changed_fields:
            from dataclasses import replace as _replace

            st.session_state.workflow = _replace(state, pending_revision=reply.revision)
            st.rerun()

    with history:
        if not st.session_state.chat:
            with st.chat_message("assistant"):
                st.markdown(
                    "I can walk you through this. Ask me why a region ranks where it does, "
                    "where any number came from, what was left out, or what this analysis "
                    "cannot tell you.\n\nYou can also ask me to change it - \"double the "
                    "weight on income\", \"drop median age\", \"compare only two of these\". "
                    "I will show you exactly what would change and wait for you to confirm."
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


def render_executed(state: WorkflowState, settings: Settings, use_llm: bool) -> None:
    """Step 5 onwards. The result, and the controls for revising it."""
    result = state.result
    assert result is not None

    if state.notice:
        st.info(state.notice)

    if result.refused:
        tabs = st.tabs(
            ["Recommendation", "Assistant", "Plan", "Decision log", "Limitations", "Registry"]
        )
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
            render_assistant(state, settings, use_llm)
        with tabs[2]:
            render_plan(state.plan)
        with tabs[3]:
            render_trace(result)
        with tabs[4]:
            render_limitations(result)
        with tabs[5]:
            render_registry()
            st.divider()
            render_capabilities()
        return

    tabs = st.tabs(
        [
            "Recommendation",
            "Assistant",
            "Comparison dashboard",
            "Sensitivity",
            "Versions",
            "Evidence",
            "Plan",
            "Decision log",
            "Limitations",
            "Registry",
        ]
    )
    with tabs[0]:
        render_recommendation(result)
    with tabs[1]:
        render_assistant(state, settings, use_llm)
    with tabs[2]:
        render_dashboard(result)
    with tabs[3]:
        render_sensitivity(result)
    with tabs[4]:
        render_versions(state)
    with tabs[5]:
        render_evidence(result)
    with tabs[6]:
        render_plan(state.plan)
    with tabs[7]:
        render_trace(result)
    with tabs[8]:
        render_limitations(result)
    with tabs[9]:
        render_registry()
        st.divider()
        render_capabilities()

    st.divider()
    st.download_button(
        "Download full result as JSON",
        data=json.dumps(result.model_dump(mode="json"), indent=2, default=str),
        file_name=f"rli_result_{result.reproducibility_hash or 'result'}.json",
        mime="application/json",
    )


def main() -> None:
    st.title("Retail Location Intelligence")
    st.caption(
        "Evidence-bound region comparison for retail site selection, built on the StateBook "
        "Atlas API. The agent constructs and negotiates the analysis; Atlas, validation, and "
        "deterministic scoring own every value in it. Illustrative scenario only: this "
        "prototype uses no proprietary retailer data and is not affiliated with any retailer."
    )

    try:
        load_registry()
    except UnverifiedMetricError as exc:
        st.error(str(exc))
        st.stop()

    if "workflow" not in st.session_state:
        st.session_state.workflow = WorkflowState()

    settings = assistant_settings()
    state: WorkflowState = st.session_state.workflow
    use_llm = sidebar(settings, state)

    if state.stage == Stage.DESCRIBE:
        if state.notice:
            st.info(state.notice)
        render_describe(state, settings, use_llm)
        st.divider()
        with st.expander("What this system can and cannot do"):
            render_capabilities()
        return

    if state.stage == Stage.REFUSED:
        render_planning_refusal(state)
        return

    if state.stage == Stage.CLARIFY:
        render_clarify(state, settings, use_llm)
        render_planning_trace(state)
        return

    if state.stage == Stage.REVIEW:
        render_review(state, settings, use_llm)
        render_planning_trace(state)
        return

    render_executed(state, settings, use_llm)


if __name__ == "__main__":
    main()
