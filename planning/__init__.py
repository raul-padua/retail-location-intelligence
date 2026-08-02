"""Agentic planning: strategy interpretation, plan proposals, approval, and revision.

The agent's authority lives entirely in this package, and it is bounded by construction:
it may propose *what to analyse*, never *what is true*. Everything it emits is revalidated
against the metric registry, the geography allowlist, and the capability registry before
it can influence a single Atlas call.
"""

from planning.brief import build_capability_brief
from planning.capabilities import CapabilityRegistry, get_capability_registry
from planning.deterministic import (
    PlanningRequest,
    build_deterministic_plan,
    read_priorities,
    weights_for,
)
from planning.llm_planner import build_llm_plan
from planning.planner import PlanningOutcome, propose_plan
from planning.revision import (
    RevisionIntent,
    apply_revision,
    looks_like_a_revision,
    parse_revision,
    propose_revision,
)
from planning.validation import validate_plan

__all__ = [
    "CapabilityRegistry",
    "PlanningOutcome",
    "PlanningRequest",
    "RevisionIntent",
    "apply_revision",
    "build_capability_brief",
    "build_deterministic_plan",
    "build_llm_plan",
    "get_capability_registry",
    "looks_like_a_revision",
    "parse_revision",
    "propose_plan",
    "propose_revision",
    "read_priorities",
    "validate_plan",
    "weights_for",
]
