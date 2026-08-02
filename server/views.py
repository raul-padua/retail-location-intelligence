"""Projections from the domain model graph onto JSON the frontend renders.

Almost every domain type is already a Pydantic model, so the bulk of this is
``model_dump(mode="json")``. What it cannot do is carry a ``@property``: ``can_approve``,
``is_usable``, ``completeness`` and their siblings are computed, and they are precisely the
values the UI needs in order to disable a button or grey out a row. Rather than
reimplement those rules in TypeScript - which would mean two definitions of "approvable",
drifting apart on the first change - each one is evaluated here and shipped as a field.

The rule this module follows: derived truth is computed in Python and transmitted. The
frontend formats and lays out. It never decides.
"""

from __future__ import annotations

from typing import Any

from api.geographies import DEMO_GEOGRAPHIES, DEMO_TOKEN_SCOPE_NOTE
from orchestration.workflow import Stage, WorkflowState
from core.config import DEFAULT_LLM_MODEL, Settings
from explanation.assistant import AssistantContext, AssistantReply
from metrics.registry import MetricRegistry
from models.analysis import AUTHORITY_LABELS, AnalysisResult
from models.metrics import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_LABELS,
    CATEGORY_WEIGHT_GUIDANCE,
    MetricCategory,
    MetricDefinition,
)
from models.plan import AnalysisPlanProposal, PlanRevisionProposal
from models.sensitivity import SensitivityReport
from models.strategy import PROFILE_FIELD_LABELS, RetailStrategyProfile
from planning.capabilities import CapabilityRegistry
from scoring.sensitivity import STRATEGY_PROFILES

# Presets and worked examples. They live server-side because the preset slugs have to stay
# inside the licensed allowlist, and that allowlist is a backend concern.
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

LLM_MODEL_CHOICES: dict[str, str] = {
    "gpt-5.6-luna": "Cost-optimized. Recommended: the model's job here is narrow.",
    "gpt-5.6-terra": "Balanced. Better phrasing on open-ended assistant questions.",
    "gpt-5.6-sol": "Frontier. Rarely worth it for this workload.",
    "gpt-5.4-mini": "Previous generation, small.",
    "gpt-4o-mini": "Legacy. Still works; two generations behind.",
}

STAGE_STEPS: list[dict[str, str]] = [
    {"stage": Stage.DESCRIBE, "label": "Describe the decision"},
    {"stage": Stage.CLARIFY, "label": "Clarify"},
    {"stage": Stage.REVIEW, "label": "Review and approve"},
    {"stage": Stage.EXECUTED, "label": "Result"},
]


# ------------------------------------------------------------------------------ plan


def metric_view(metric: MetricDefinition) -> dict[str, Any]:
    """One shape for a metric wherever it crosses the wire.

    Metrics reach the client from two directions - the catalog, and embedded in every
    evidence item - and a component that reads ``category_label`` should not have to know
    which route its copy arrived by.
    """
    return {
        **metric.model_dump(mode="json"),
        "category_label": CATEGORY_LABELS[metric.category],
        "is_count": metric.is_count,
        "is_rate": metric.is_rate,
    }


def profile_view(profile: RetailStrategyProfile) -> list[dict[str, Any]]:
    """Flatten the attributed profile into rows, each carrying its own provenance.

    The provenance is the point of this model. A row that reads "suburban" means nothing
    to a reviewer until it also says whether the user typed it or the planner guessed it.
    """
    return [
        {
            "name": name,
            "label": PROFILE_FIELD_LABELS.get(name, name.replace("_", " ").capitalize()),
            "value": attributed.describe() if attributed.is_known else None,
            "provenance": str(attributed.provenance),
            "note": attributed.note,
            "is_known": attributed.is_known,
            "is_assumption": attributed.is_assumption,
        }
        for name, attributed in profile._attributed_fields().items()
    ]


def plan_view(plan: AnalysisPlanProposal | None) -> dict[str, Any] | None:
    if plan is None:
        return None

    data = plan.model_dump(mode="json")
    data["can_approve"] = plan.can_approve
    data["can_execute"] = plan.can_execute
    data["unanswered_required_question_ids"] = [
        question.question_id for question in plan.unanswered_required_questions
    ]
    data["planner_provenance"]["description"] = plan.planner_provenance.describe()
    data["planner_provenance"]["is_deterministic"] = plan.planner_provenance.is_deterministic
    data["validation"]["passed"] = plan.validation.passed
    data["validation"]["failures"] = [
        check.model_dump(mode="json") for check in plan.validation.failures
    ]
    data["profile_rows"] = profile_view(plan.retail_strategy_profile)
    return data


def revision_view(revision: PlanRevisionProposal | None) -> dict[str, Any] | None:
    if revision is None:
        return None
    data = revision.model_dump(mode="json")
    data["is_actionable"] = revision.is_actionable
    data["validation"]["passed"] = revision.validation.passed
    data["validation"]["failures"] = [
        check.model_dump(mode="json") for check in revision.validation.failures
    ]
    return data


# ---------------------------------------------------------------------------- result


def result_view(
    result: AnalysisResult | None, *, include_raw_calls: bool = False
) -> dict[str, Any] | None:
    """Project a result. Raw Atlas bodies are opt-in because they dominate the payload.

    A three-region run carries roughly 150 KB of raw request and response bodies, against
    perhaps 40 KB for everything the dashboard actually draws. The evidence panel fetches
    them on demand instead.
    """
    if result is None:
        return None

    data = result.model_dump(mode="json")
    data["refused"] = result.refused
    data["plan_version"] = result.plan_version
    data["proposal"] = plan_view(result.proposal)

    if result.evidence is not None:
        evidence = data["evidence"]
        evidence["completeness"] = result.evidence.completeness
        evidence["usable_count"] = len(result.evidence.usable_items())
        evidence["raw_call_count"] = len(result.evidence.raw_calls)
        for item, projected in zip(result.evidence.items, evidence["items"], strict=True):
            projected["metric"] = metric_view(item.metric)
            projected["is_usable"] = item.is_usable
            projected["geography_context_shifted"] = item.geography_context_shifted
            projected["citation"] = item.citation()
        if not include_raw_calls:
            evidence["raw_calls"] = []

    data["authority_counts"] = {
        str(authority): len(result.trace_by_authority(authority))
        for authority in {entry.authority for entry in result.trace}
    }
    return data


# ----------------------------------------------------------------------------- state


def state_view(state: WorkflowState) -> dict[str, Any]:
    plan_diff = state.plan_diff()
    result_diff = state.result_diff()

    return {
        "stage": str(state.stage),
        "notice": state.notice,
        "objective": state.objective,
        "geographies": list(state.geographies),
        "retailer_type": state.retailer_type,
        "store_format": state.store_format,
        "target_segments": state.target_segments,
        "can_approve": state.can_approve,
        "plan": plan_view(state.plan),
        "planning_trace": [
            {
                **entry.model_dump(mode="json"),
                "authority_label": AUTHORITY_LABELS[entry.authority],
            }
            for entry in state.planning_trace
        ],
        "refusal": state.refusal.model_dump(mode="json") if state.refusal else None,
        "pending_revision": revision_view(state.pending_revision),
        "versions": [
            {
                "label": version.label,
                "version": version.plan.version,
                "plan": plan_view(version.plan),
                "result": result_view(version.result),
            }
            for version in state.history
        ],
        "plan_diff": (
            {
                **plan_diff.model_dump(mode="json"),
                "is_empty": plan_diff.is_empty,
                "description": plan_diff.describe(),
                "weight_changes": [
                    {**change.model_dump(mode="json"), "change": change.change}
                    for change in plan_diff.weight_changes
                ],
            }
            if plan_diff
            else None
        ),
        "result_diff": (
            {
                **result_diff.model_dump(mode="json"),
                "evidence_changed": result_diff.evidence_changed,
                "deltas": [
                    {
                        **delta.model_dump(mode="json"),
                        "rank_change": delta.rank_change,
                        "score_change": delta.score_change,
                    }
                    for delta in result_diff.deltas
                ],
            }
            if result_diff
            else None
        ),
    }


# ------------------------------------------------------------------------ sensitivity


def sensitivity_view(report: SensitivityReport) -> dict[str, Any]:
    data = report.model_dump(mode="json")
    data["assumption_sensitive"] = report.recommendation_is_assumption_sensitive
    data["comparison"]["winners"] = report.comparison.winners
    data["comparison"]["baseline"]["winner"] = (
        report.comparison.baseline.winner.model_dump(mode="json")
        if report.comparison.baseline.winner
        else None
    )
    for ranking, projected in zip(
        report.comparison.profiles, data["comparison"]["profiles"], strict=True
    ):
        projected["winner"] = (
            ranking.winner.model_dump(mode="json") if ranking.winner else None
        )
    for group, entries in report.comparison.deltas.items():
        data["comparison"]["deltas"][group] = [
            {
                **delta.model_dump(mode="json"),
                "rank_change": delta.rank_change,
                "score_change": delta.score_change,
            }
            for delta in entries
        ]
    return data


# -------------------------------------------------------------------------- assistant


def assistant_reply_view(reply: AssistantReply) -> dict[str, Any]:
    return {
        "text": reply.text,
        "generated_by": reply.generated_by,
        "refused": reply.refused,
        "notes": list(reply.notes),
        "proposes_revision": reply.proposes_revision,
        "revision": revision_view(reply.revision),
    }


def assistant_context_view(context: AssistantContext) -> dict[str, Any]:
    return {
        "suggestions": list(context.suggestions),
        "has_result": context.has_result,
        "region_names": list(context.region_names),
        "fact_count": len(context.facts),
    }


# --------------------------------------------------------------------------- catalog


def settings_view(settings: Settings) -> dict[str, Any]:
    """What the client is allowed to know about configuration. No credential leaves here."""
    return {
        "atlas_token_present": bool(settings.atlas_token and settings.atlas_token.strip()),
        "is_demo_token": settings.is_demo_token,
        "atlas_base_url": settings.atlas_base_url,
        "llm_enabled": settings.llm_enabled,
        "llm_model": settings.llm_model,
        "llm_key_from_environment": False,
        "default_llm_model": DEFAULT_LLM_MODEL,
    }


def catalog_view(
    registry: MetricRegistry, capabilities: CapabilityRegistry
) -> dict[str, Any]:
    """Everything static the frontend needs, fetched once at startup."""
    return {
        "categories": [
            {
                "id": str(category),
                "label": CATEGORY_LABELS[category],
                "description": CATEGORY_DESCRIPTIONS[category],
                "guidance": CATEGORY_WEIGHT_GUIDANCE[category],
            }
            for category in MetricCategory
        ],
        "metrics": [metric_view(metric) for metric in registry.all()],
        "capabilities": [
            {**capability.model_dump(mode="json"), "is_available": capability.is_available}
            for capability in capabilities.all()
        ],
        "strategy_profiles": [
            profile.model_dump(mode="json") for profile in STRATEGY_PROFILES
        ],
        "geographies": [
            geography.model_dump(mode="json") for geography in DEMO_GEOGRAPHIES.values()
        ],
        "presets": [{"label": label, "slugs": slugs} for label, slugs in PRESETS.items()],
        "objective_examples": [
            {"label": label, "objective": text} for label, text in OBJECTIVE_EXAMPLES.items()
        ],
        "llm_models": [
            {"id": model_id, "caption": caption}
            for model_id, caption in LLM_MODEL_CHOICES.items()
        ],
        "stage_steps": STAGE_STEPS,
        "authority_labels": {
            str(authority): label for authority, label in AUTHORITY_LABELS.items()
        },
        "demo_token_scope_note": DEMO_TOKEN_SCOPE_NOTE,
    }


__all__ = [
    "assistant_context_view",
    "assistant_reply_view",
    "catalog_view",
    "plan_view",
    "profile_view",
    "result_view",
    "revision_view",
    "sensitivity_view",
    "settings_view",
    "state_view",
]
