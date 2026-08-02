"""Deterministic validation of a plan proposal.

This is the boundary between "an agent suggested something" and "the system will act on
it". Whatever produced the proposal - a language model, the deterministic planner, or a
human editing weights in the UI - it arrives here as untrusted structure and every field
is re-checked against the registries.

The rules are fixed and documented, because the alternative to a documented rule is a
silent correction, and a silent correction is how a plan ends up analysing something
other than what the reviewer read.

Weight handling specifically:

* A negative, infinite, or non-numeric weight is **rejected**. It is not a weight.
* An unrecognised category key is **rejected**.
* A category with no weight supplied is treated as **zero**, and that is disclosed.
* Weights that do not sum to 1 are **renormalized proportionally**, and that is disclosed.
* Weights that sum to zero are **rejected**; there is nothing to renormalize.
"""

from __future__ import annotations

import math

from api.geographies import DEMO_TOKEN_SCOPE_NOTE
from metrics.registry import MetricRegistry, get_registry
from models.metrics import MetricCategory
from models.plan import (
    AnalysisPlanProposal,
    PlanCheck,
    PlanStatus,
    PlanValidationReport,
    PlanValidationStatus,
)

MIN_GEOGRAPHIES = 2
WEIGHT_SUM_TOLERANCE = 1e-6


def validate_plan(
    plan: AnalysisPlanProposal,
    registry: MetricRegistry | None = None,
) -> AnalysisPlanProposal:
    """Re-check every field and return the plan carrying its validation report.

    Never raises on a bad plan: an invalid proposal is a thing the UI has to render and
    explain, not an exception. The report says what failed and the status says whether a
    human may approve it.
    """
    registry = registry or get_registry()

    checks: list[PlanCheck] = []
    warnings: list[str] = []
    disclosures: list[str] = []

    checks.append(_check_geographies(plan))
    checks.append(_check_metrics_exist(plan, registry))
    checks.append(_check_metrics_support_levels(plan, registry, warnings))

    weights, weight_check, weight_disclosures = _check_and_normalize_weights(plan, registry)
    checks.append(weight_check)
    disclosures.extend(weight_disclosures)

    overrides_check, override_disclosures = _check_metric_weight_overrides(plan, registry)
    checks.append(overrides_check)
    disclosures.extend(override_disclosures)

    checks.append(_check_clarifications(plan))
    checks.append(_check_unsupported_disclosed(plan))
    checks.append(_check_assumptions_visible(plan))

    blocking_failures = [check for check in checks if not check.passed and check.blocking]
    status = (
        PlanValidationStatus.FAILED if blocking_failures else PlanValidationStatus.PASSED
    )

    report = PlanValidationReport(
        status=status,
        checks=checks,
        warnings=warnings,
        disclosures=disclosures,
    )

    # An outstanding required question takes precedence over a failed check, because the
    # question is the route out. DRAFT is reserved for a plan that failed validation with
    # no question attached, which is a dead end the user has to edit their way out of.
    if plan.unanswered_required_questions:
        plan_status = PlanStatus.NEEDS_CLARIFICATION
    elif blocking_failures:
        plan_status = PlanStatus.DRAFT
    else:
        plan_status = PlanStatus.READY_FOR_REVIEW

    update: dict = {"validation": report, "status": plan_status}
    if weights is not None:
        update["category_weights"] = weights
    return plan.model_copy(update=update)


# ------------------------------------------------------------------------ individual gates


def _check_geographies(plan: AnalysisPlanProposal) -> PlanCheck:
    resolved = plan.candidate_geographies
    unique = {geography.slug for geography in resolved}

    if len(unique) < MIN_GEOGRAPHIES:
        return PlanCheck(
            name="candidate_geographies",
            passed=False,
            detail=(
                f"A comparison needs at least {MIN_GEOGRAPHIES} distinct candidate "
                f"regions; {len(unique)} resolved. {DEMO_TOKEN_SCOPE_NOTE}"
            ),
        )
    return PlanCheck(
        name="candidate_geographies",
        passed=True,
        detail=(
            f"{len(unique)} distinct region(s) resolved against the licensed allowlist: "
            + ", ".join(sorted(unique))
            + "."
        ),
    )


def _check_metrics_exist(plan: AnalysisPlanProposal, registry: MetricRegistry) -> PlanCheck:
    """Every selected id must be a registry metric.

    This is the check that makes a hallucinated metric structurally inert. It also
    catches an Atlas datapoint identifier supplied where a metric id belongs: the two
    namespaces are deliberately separate, and only the registry bridges them.
    """
    if not plan.selected_metric_ids:
        return PlanCheck(
            name="selected_metrics",
            passed=False,
            detail="No metric was selected, so there is nothing to compare the regions on.",
        )

    unknown = [
        metric_id for metric_id in plan.selected_metric_ids if registry.get(metric_id) is None
    ]
    if unknown:
        return PlanCheck(
            name="selected_metrics",
            passed=False,
            detail=(
                "These are not approved metrics and cannot be requested: "
                + ", ".join(sorted(unknown))
                + ". Only ids present in the verified registry are permitted."
            ),
        )

    return PlanCheck(
        name="selected_metrics",
        passed=True,
        detail=(
            f"All {len(plan.selected_metric_ids)} selected metric(s) exist in the verified "
            "registry."
        ),
    )


def _check_metrics_support_levels(
    plan: AnalysisPlanProposal, registry: MetricRegistry, warnings: list[str]
) -> PlanCheck:
    """At least one selected metric must be published at every candidate's level."""
    if not plan.candidate_geographies or not plan.selected_metric_ids:
        return PlanCheck(
            name="metric_geography_support",
            passed=True,
            detail="Not applicable until regions and metrics are both selected.",
            blocking=False,
        )

    types = [geography.geography_type for geography in plan.candidate_geographies]
    usable = [
        metric_id
        for metric_id in plan.selected_metric_ids
        if (metric := registry.get(metric_id)) is not None
        and all(metric.supports(level) for level in types)
    ]

    unusable = sorted(set(plan.selected_metric_ids) - set(usable))
    if unusable:
        warnings.append(
            f"{len(unusable)} selected metric(s) are not published at every candidate's "
            "geographic level and will be excluded before any API call: "
            + ", ".join(unusable)
            + "."
        )

    if not usable:
        return PlanCheck(
            name="metric_geography_support",
            passed=False,
            detail=(
                "No selected metric is published at the geographic level of every "
                "candidate region, so nothing comparable could be retrieved. Compare "
                "regions of the same type, or select different metrics."
            ),
        )

    return PlanCheck(
        name="metric_geography_support",
        passed=True,
        detail=(
            f"{len(usable)} of {len(plan.selected_metric_ids)} selected metric(s) are "
            "published at every candidate's geographic level."
        ),
    )


def _check_and_normalize_weights(
    plan: AnalysisPlanProposal, registry: MetricRegistry
) -> tuple[dict[MetricCategory, float] | None, PlanCheck, list[str]]:
    disclosures: list[str] = []
    raw = plan.category_weights

    if not raw:
        return (
            None,
            PlanCheck(
                name="category_weights",
                passed=False,
                detail="No category weights were supplied, so no score could be computed.",
            ),
            disclosures,
        )

    invalid: list[str] = []
    cleaned: dict[MetricCategory, float] = {}
    for category, weight in raw.items():
        try:
            category_key = MetricCategory(category)
        except ValueError:
            invalid.append(f"{category!r} is not a scoring category")
            continue
        try:
            numeric = float(weight)
        except (TypeError, ValueError):
            invalid.append(f"{category_key}: {weight!r} is not a number")
            continue
        if math.isnan(numeric) or math.isinf(numeric):
            invalid.append(f"{category_key}: {weight!r} is not a finite number")
            continue
        if numeric < 0:
            invalid.append(f"{category_key}: {numeric} is negative")
            continue
        cleaned[category_key] = numeric

    if invalid:
        return (
            None,
            PlanCheck(
                name="category_weights",
                passed=False,
                detail=(
                    "These weights were rejected rather than corrected: "
                    + "; ".join(sorted(invalid))
                    + "."
                ),
            ),
            disclosures,
        )

    missing = [category for category in MetricCategory if category not in cleaned]
    if missing:
        for category in missing:
            cleaned[category] = 0.0
        disclosures.append(
            "No weight was supplied for "
            + ", ".join(str(category) for category in missing)
            + ", so each was set to zero. Those categories will not contribute to the score."
        )

    total = sum(cleaned.values())
    if total <= 0:
        return (
            None,
            PlanCheck(
                name="category_weights",
                passed=False,
                detail=(
                    "Every category weight is zero, so there is nothing to weight the "
                    "score by. At least one category must be greater than zero."
                ),
            ),
            disclosures,
        )

    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        cleaned = {category: weight / total for category, weight in cleaned.items()}
        disclosures.append(
            f"Category weights summed to {total:.4g} rather than 1, so they were "
            "renormalized proportionally. The relative emphasis between categories is "
            "unchanged: "
            + ", ".join(
                f"{category} {weight:.0%}"
                for category, weight in sorted(cleaned.items())
                if weight > 0
            )
            + "."
        )

    weighted_without_metrics = [
        category
        for category, weight in cleaned.items()
        if weight > 0 and not registry.by_category(category)
    ]
    if weighted_without_metrics:
        disclosures.append(
            "These categories carry weight but have no metric in the registry, so their "
            "weight is redistributed at scoring time: "
            + ", ".join(str(category) for category in weighted_without_metrics)
            + "."
        )

    return (
        cleaned,
        PlanCheck(
            name="category_weights",
            passed=True,
            detail=(
                "All category weights are finite, non-negative, and normalized to sum to 1."
            ),
        ),
        disclosures,
    )


def _check_metric_weight_overrides(
    plan: AnalysisPlanProposal, registry: MetricRegistry
) -> tuple[PlanCheck, list[str]]:
    disclosures: list[str] = []
    overrides = plan.metric_weight_overrides
    if not overrides:
        return (
            PlanCheck(
                name="metric_weight_overrides",
                passed=True,
                detail="No per-metric weight overrides were requested.",
            ),
            disclosures,
        )

    problems: list[str] = []
    for metric_id, weight in overrides.items():
        metric = registry.get(metric_id)
        if metric is None:
            problems.append(f"{metric_id!r} is not an approved metric")
            continue
        try:
            numeric = float(weight)
        except (TypeError, ValueError):
            problems.append(f"{metric_id}: {weight!r} is not a number")
            continue
        if math.isnan(numeric) or math.isinf(numeric) or numeric <= 0:
            problems.append(
                f"{metric_id}: {weight!r} must be a finite number greater than zero"
            )
            continue
        disclosures.append(
            f"{metric.display_name} carries a weight of {numeric:g} within "
            f"{metric.category} instead of its registry default of {metric.weight:g}."
        )

    if problems:
        return (
            PlanCheck(
                name="metric_weight_overrides",
                passed=False,
                detail="Rejected weight override(s): " + "; ".join(sorted(problems)) + ".",
            ),
            [],
        )

    return (
        PlanCheck(
            name="metric_weight_overrides",
            passed=True,
            detail=f"{len(overrides)} metric weight override(s) accepted and disclosed.",
        ),
        disclosures,
    )


def _check_clarifications(plan: AnalysisPlanProposal) -> PlanCheck:
    outstanding = plan.unanswered_required_questions
    if outstanding:
        return PlanCheck(
            name="required_clarifications",
            passed=False,
            detail=(
                f"{len(outstanding)} required question(s) are unanswered: "
                + "; ".join(question.question for question in outstanding)
            ),
        )
    optional = [
        question
        for question in plan.clarification_questions
        if not question.required and not question.answered
    ]
    return PlanCheck(
        name="required_clarifications",
        passed=True,
        detail=(
            "No required question is outstanding."
            + (
                f" {len(optional)} optional question(s) will proceed on a disclosed default."
                if optional
                else ""
            )
        ),
    )


def _check_unsupported_disclosed(plan: AnalysisPlanProposal) -> PlanCheck:
    """Unsupported requirements must be attached to the plan, not dropped from it."""
    incomplete = [
        requirement.requirement
        for requirement in plan.unsupported_requirements
        if not requirement.why_unavailable or not requirement.would_require
    ]
    if incomplete:
        return PlanCheck(
            name="unsupported_disclosed",
            passed=False,
            detail=(
                "These unsupported requirements were recorded without saying why they "
                "are unavailable or what would supply them: " + ", ".join(incomplete)
            ),
        )
    return PlanCheck(
        name="unsupported_disclosed",
        passed=True,
        detail=(
            f"{len(plan.unsupported_requirements)} unsupported requirement(s) are "
            "disclosed with a reason and a data source that would satisfy them."
        ),
    )


def _check_assumptions_visible(plan: AnalysisPlanProposal) -> PlanCheck:
    """Every inference must carry a basis, so a reviewer can overrule it knowingly."""
    unexplained = [
        assumption.subject for assumption in plan.assumptions if not assumption.basis
    ]
    if unexplained:
        return PlanCheck(
            name="assumptions_visible",
            passed=False,
            detail=(
                "These assumptions were recorded without a basis: "
                + ", ".join(unexplained)
            ),
        )

    inferred = plan.retail_strategy_profile.assumptions()
    unexplained_profile = [name for name, field in inferred.items() if not field.note]
    if unexplained_profile:
        return PlanCheck(
            name="assumptions_visible",
            passed=False,
            detail=(
                "These inferred profile fields were recorded without a reason: "
                + ", ".join(unexplained_profile)
            ),
        )

    return PlanCheck(
        name="assumptions_visible",
        passed=True,
        detail=(
            f"{len(plan.assumptions)} plan assumption(s) and {len(inferred)} inferred "
            "profile field(s) are shown with their basis."
        ),
    )
