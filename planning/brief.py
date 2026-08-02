"""The capability brief handed to the planner.

A model can only stay inside a boundary it can see. Rather than describing the system in
prose and hoping, the planner receives a generated, machine-readable inventory of exactly
what exists: the licensed geographies, the approved metric ids with their categories,
units, directions, levels and retail rationales, the deterministic operations that can be
requested, and the data dimensions that are known to be absent.

The brief is generated from the registries themselves, so it cannot drift out of date. It
is also worth showing to a reviewer verbatim, because "what the agent was told it could
do" is part of the audit trail.
"""

from __future__ import annotations

from api.geographies import DEMO_TOKEN_SCOPE_NOTE, demo_geography_choices
from metrics.registry import MetricRegistry, get_registry
from models.metrics import CATEGORY_DESCRIPTIONS, CATEGORY_LABELS, MetricCategory
from orchestration.intent import UNSUPPORTED_DIMENSION_REQUIREMENTS
from planning.capabilities import CapabilityRegistry, get_capability_registry


def build_capability_brief(
    registry: MetricRegistry | None = None,
    capabilities: CapabilityRegistry | None = None,
) -> str:
    """Generate the complete description of the planner's action space."""
    registry = registry or get_registry()
    capabilities = capabilities or get_capability_registry()

    sections = [
        _geographies_section(),
        _categories_section(),
        _metrics_section(registry),
        capabilities.describe_for_planner(),
        _unsupported_section(),
    ]
    return "\n\n".join(sections)


def _geographies_section() -> str:
    lines = [
        "SUPPORTED GEOGRAPHIES. These are the only regions that exist. A name not on this "
        "list cannot be analysed and must not be proposed:",
    ]
    for geography in demo_geography_choices():
        lines.append(
            f"- {geography.slug} | {geography.display_name} | level: {geography.geography_type}"
        )
    lines.append(f"Scope note: {DEMO_TOKEN_SCOPE_NOTE}")
    return "\n".join(lines)


def _categories_section() -> str:
    lines = ["SCORING CATEGORIES. Weights are proposed against these five and no others:"]
    for category in MetricCategory:
        lines.append(
            f"- {category} | {CATEGORY_LABELS[category]} | {CATEGORY_DESCRIPTIONS[category]}"
        )
    return "\n".join(lines)


def _metrics_section(registry: MetricRegistry) -> str:
    lines = [
        "APPROVED METRICS. Select by metric_id only. These ids are the complete set; there "
        "is no other metric, and an id not listed here will be rejected:",
    ]
    for metric in registry.all():
        levels = ", ".join(str(level) for level in metric.supported_geography_types)
        lines.append(
            f"- metric_id: {metric.metric_id}\n"
            f"  name: {metric.display_name}\n"
            f"  category: {metric.category}\n"
            f"  unit: {metric.unit} | direction: {metric.direction}\n"
            f"  available at: {levels}\n"
            f"  default weight within category: {metric.weight:g}\n"
            f"  why a retailer cares: {metric.retail_rationale}"
        )
    return "\n".join(lines)


def _unsupported_section() -> str:
    lines = [
        "KNOWN ABSENT DATA DIMENSIONS. The system holds nothing on these. Name them as "
        "unsupported when the user asks for them. Never substitute a proxy metric and "
        "never imply an approved metric measures one of these:",
    ]
    for requirement in sorted(set(UNSUPPORTED_DIMENSION_REQUIREMENTS)):
        lines.append(f"- {requirement}")
    return "\n".join(lines)
