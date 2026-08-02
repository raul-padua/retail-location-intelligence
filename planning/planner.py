"""Planner entry point.

One function the rest of the system calls, with the ordering that matters baked in:

1. **Classify the untrusted text first.** An injection attempt or a request for a
   company-specific forecast is refused here, before a planner exists and before an API
   client is constructed. That ordering is the guarantee: a prompt designed to talk a
   model out of its rules never arrives in front of one.
2. **Build a plan.** With a key, the model proposes and every field is revalidated. Without
   one, the deterministic planner produces the same shape from pattern matching.
3. **Validate deterministically.** Whatever built it, the plan passes through the same
   gate before anyone is offered an approve button.

The result is a proposal, never an execution. Nothing in this module can call Atlas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.config import Settings, get_settings
from core.logging import get_logger, log_event
from metrics.registry import MetricRegistry, get_registry
from models.analysis import Refusal, TraceAuthority, TraceEntry
from models.plan import AnalysisPlanProposal
from orchestration.intent import RefusalKind, interpret_question
from planning.capabilities import CapabilityRegistry, get_capability_registry
from planning.deterministic import PlanningRequest, build_deterministic_plan
from planning.llm_planner import build_llm_plan
from planning.validation import validate_plan

logger = get_logger("planning.planner")


@dataclass
class PlanningOutcome:
    """Either a proposal or a refusal, never both."""

    plan: AnalysisPlanProposal | None = None
    refusal: Refusal | None = None
    refusal_kind: RefusalKind | None = None
    trace: list[TraceEntry] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.trace is None:
            self.trace = []

    @property
    def refused(self) -> bool:
        return self.refusal is not None


def propose_plan(
    request: PlanningRequest,
    settings: Settings | None = None,
    registry: MetricRegistry | None = None,
    capabilities: CapabilityRegistry | None = None,
    use_llm: bool = True,
) -> PlanningOutcome:
    """Turn a business objective into a validated, unapproved plan proposal."""
    settings = settings or get_settings()
    registry = registry or get_registry()
    capabilities = capabilities or get_capability_registry()

    trace: list[TraceEntry] = [
        TraceEntry(
            step="objective_received",
            detail="The user's business objective, exactly as submitted.",
            authority=TraceAuthority.USER,
            payload={
                "objective": request.objective,
                "regions_selected": list(request.geographies),
                "answers_supplied": dict(request.answers),
            },
        )
    ]

    intent = interpret_question(request.objective)
    trace.append(
        TraceEntry(
            step="classify_objective",
            detail=(
                "Objective sanitized and classified before any planner ran."
                if intent.plan_ok
                else f"Objective refused before planning: {intent.refusal_kind}."
            ),
            authority=TraceAuthority.VALIDATION,
            payload={
                "sanitized_objective": intent.sanitized_question,
                "planning_permitted": intent.plan_ok,
                "refusal_kind": str(intent.refusal_kind) if intent.refusal_kind else None,
                "injection_flagged": intent.flagged_injection,
                "notes": intent.notes,
            },
        )
    )

    if not intent.plan_ok and intent.refusal is not None:
        log_event(
            logger,
            logging.WARNING,
            "planning_refused",
            kind=str(intent.refusal_kind),
            injection=intent.flagged_injection,
        )
        return PlanningOutcome(
            refusal=intent.refusal, refusal_kind=intent.refusal_kind, trace=trace
        )

    use_model = use_llm and settings.llm_enabled
    if use_model:
        plan = build_llm_plan(request, settings, registry, capabilities)
    else:
        plan = build_deterministic_plan(request, registry, capabilities)

    trace.append(
        TraceEntry(
            step="planner_output",
            detail=(
                f"Plan proposed by {plan.planner_provenance.describe()}."
            ),
            authority=TraceAuthority.AGENT,
            payload={
                "planner": plan.planner_provenance.planner,
                "model": plan.planner_provenance.model,
                "fell_back": plan.planner_provenance.fell_back,
                "fallback_reason": plan.planner_provenance.fallback_reason,
                "proposed_metric_ids": plan.selected_metric_ids,
                "proposed_category_weights": {
                    str(category): round(weight, 4)
                    for category, weight in plan.category_weights.items()
                },
                "clarification_questions": [
                    {"id": q.question_id, "question": q.question, "required": q.required}
                    for q in plan.clarification_questions
                ],
                "assumptions": [a.assumption for a in plan.assumptions],
            },
        )
    )

    if plan.planner_provenance.rejected_fields:
        trace.append(
            TraceEntry(
                step="planner_output_rejected_fields",
                detail=(
                    f"{len(plan.planner_provenance.rejected_fields)} field(s) returned by "
                    "the planner failed revalidation and were discarded."
                ),
                authority=TraceAuthority.VALIDATION,
                payload={
                    "rejected": [
                        {
                            "field": entry.field,
                            "value": entry.offending_value,
                            "reason": entry.reason,
                        }
                        for entry in plan.planner_provenance.rejected_fields
                    ]
                },
            )
        )

    validated = validate_plan(plan, registry)
    trace.append(
        TraceEntry(
            step="validate_plan",
            detail=(
                f"Plan validation {validated.validation.status}. "
                f"Status is now {validated.status}."
            ),
            authority=TraceAuthority.VALIDATION,
            payload={
                "status": str(validated.validation.status),
                "checks": [
                    {"name": check.name, "passed": check.passed, "detail": check.detail}
                    for check in validated.validation.checks
                ],
                "disclosures": validated.validation.disclosures,
                "warnings": validated.validation.warnings,
                "can_approve": validated.can_approve,
            },
        )
    )

    return PlanningOutcome(plan=validated, trace=trace)
