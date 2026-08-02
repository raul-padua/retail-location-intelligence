"""Turning a conversational request into a proposed plan revision.

A chat surface attached to an analysis is a control surface whether or not it was designed
as one. "Double the weight on income" is an instruction, and a system that simply carries
it out has quietly given a language model - or an offhand sentence - the authority to
change the answer.

So a revision request produces a proposal and stops. The proposal states exactly which
fields would change, from what to what, and what the analytical effect would be in
directional terms. It is validated deterministically before it is offered, and it does
nothing until the user confirms. On confirmation it produces a *new version* of the plan;
the previous plan and its result are untouched and remain comparable.

Parsing is deterministic pattern matching, not model interpretation, for the same reason
the flip-point scan is: an approximately-correct reading of "reduce" would be much worse
than no reading at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from api.geographies import UnsupportedGeographyError, resolve_geography
from metrics.registry import MetricRegistry, get_registry
from models.metrics import CATEGORY_LABELS, MetricCategory
from models.plan import (
    AnalysisPlanProposal,
    ApprovalRecord,
    PlanRevisionProposal,
    PlanStatus,
)
from orchestration.intent import detect_unsupported_dimensions, sanitize_question
from planning.deterministic import _CATEGORY_PHRASES
from planning.validation import validate_plan
from scoring.sensitivity import STRATEGY_PROFILES, get_profile

# Multipliers applied to a category weight. Stated as data so the UI and the docs can
# quote the exact rule rather than paraphrasing it.
_MAGNITUDES: list[tuple[str, float, str]] = [
    (r"\b(?:double|twice as (?:important|much)|2x)\b", 2.0, "doubled"),
    (r"\b(?:triple|three times|3x)\b", 3.0, "tripled"),
    (r"\b(?:halve|half as (?:important|much)|cut in half)\b", 0.5, "halved"),
    (
        r"\b(?:much more important|far more important|matters? (?:the )?most|"
        r"most important|dominant|top priority)\b",
        3.0,
        "raised sharply",
    ),
    (
        r"\b(?:increase|raise|boost|more important|more weight|weight .* more|"
        r"prioriti[sz]e|emphasi[sz]e|care more about|favou?r)\b",
        1.5,
        "increased",
    ),
    (
        r"\b(?:decrease|reduce|lower|less important|less weight|de-?prioriti[sz]e|"
        r"care less about|downweight|play down)\b",
        0.6,
        "reduced",
    ),
    (
        r"\b(?:ignore|drop|remove|zero out|exclude|stop using)\b",
        0.0,
        "removed from the score",
    ),
]

_REMOVE = re.compile(
    r"\b(?:remove|drop|exclude|take out|stop using|get rid of|without)\b", re.IGNORECASE
)
_ONLY = re.compile(
    r"\b(?:only|just|limit(?:ed)? to|restrict to|narrow to)\b", re.IGNORECASE
)
_ADD = re.compile(r"\b(?:add|include|bring in|also compare)\b", re.IGNORECASE)

_CONSERVATIVE = re.compile(
    r"\b(?:conservative|balanced|neutral|even|default|unweighted|equal)\b", re.IGNORECASE
)

# A message has to look like an instruction to change something before it is treated as
# one. "Why did income matter so much?" is a question about the analysis, not a request
# to reweight it, and misreading the two is worse than missing a revision.
_REVISION_SIGNAL = re.compile(
    r"\b(?:double|triple|halve|increase|raise|boost|decrease|reduce|lower|remove|drop|"
    r"exclude|add|include|prioriti[sz]e|de-?prioriti[sz]e|emphasi[sz]e|reweight|"
    r"re-?weight|change the weight|adjust|set|use|switch to|compare only|only compare|"
    r"rerun|re-?run|recalculate|what (?:if|changes if)|weight .* more|weight .* less|"
    r"matters? most|more important|less important|care more|care less|apply|switch|"
    r"profile|lens|weighting|conservative)\b",
    re.IGNORECASE,
)

_QUESTION_ONLY = re.compile(
    r"^\s*(?:why|what evidence|which metrics were|how confident|where did|who|when|"
    r"explain|walk me through|tell me about|summari[sz]e)\b",
    re.IGNORECASE,
)


@dataclass
class RevisionIntent:
    """What was parsed out of the message, before anything is validated."""

    weight_changes: dict[MetricCategory, tuple[float, str]] = field(default_factory=dict)
    metrics_removed: list[str] = field(default_factory=list)
    regions: list[str] | None = None
    profile_id: str | None = None
    reset_to_defaults: bool = False
    unsupported: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.weight_changes,
                self.metrics_removed,
                self.regions is not None,
                self.profile_id,
                self.reset_to_defaults,
            )
        )


def looks_like_a_revision(message: str) -> bool:
    """Whether the message is asking to change the analysis rather than explain it."""
    text = sanitize_question(message)
    if not text:
        return False
    if _QUESTION_ONLY.match(text) and not re.search(
        r"\bwhat (?:if|changes if)\b", text, re.IGNORECASE
    ):
        return False
    return bool(_REVISION_SIGNAL.search(text))


# A reweighting request names a category more bluntly than an objective statement does:
# "reduce current population" rather than "we care about market size". These phrases are
# kept out of the objective-reading vocabulary because there they would collide - in
# "prioritize population growth" the word "population" is part of the growth phrase, not a
# separate vote for market size.
_REVISION_CATEGORY_PHRASES: dict[MetricCategory, tuple[str, ...]] = {
    MetricCategory.MARKET_POTENTIAL: (
        "current population", "population", "households", "market potential",
        "labor force", "labour force",
    ),
    MetricCategory.CUSTOMER_FIT: ("customer fit", "median age", "schooling"),
    MetricCategory.ECONOMIC_ATTRACTIVENESS: (
        "economic attractiveness", "household income", "median income", "unemployment",
    ),
    MetricCategory.ACCESSIBILITY: ("accessibility",),
    MetricCategory.GROWTH_OUTLOOK: ("growth outlook", "market growth", "growth"),
}


def _categories_in(text: str) -> list[MetricCategory]:
    lowered = text.lower()
    found: list[MetricCategory] = []
    for source in (_CATEGORY_PHRASES, _REVISION_CATEGORY_PHRASES):
        for category, phrases in source.items():
            if any(phrase in lowered for phrase in phrases) and category not in found:
                found.append(category)
    return found


def _magnitude_for(text: str) -> tuple[float, str] | None:
    for pattern, factor, label in _MAGNITUDES:
        if re.search(pattern, text, re.IGNORECASE):
            return factor, label
    return None


def _metrics_in(text: str, registry: MetricRegistry, plan: AnalysisPlanProposal) -> list[str]:
    lowered = text.lower()
    matched: list[str] = []
    for metric_id in plan.selected_metric_ids:
        metric = registry.get(metric_id)
        if metric is None:
            continue
        name = metric.display_name.lower()
        short = re.sub(r"\s*\(.*?\)\s*", "", name).strip()
        if metric_id in lowered or name in lowered or (short and short in lowered):
            matched.append(metric_id)
    return matched


def _regions_in(text: str, plan: AnalysisPlanProposal) -> list[str]:
    """Region names from the current candidate set that the message mentions.

    Matching is positional because the licensed names nest: "Burlington" occurs inside
    "South Burlington", so a naive substring check reads "compare only Burlington and
    South Burlington" as naming one region. A region counts as mentioned only if it has
    at least one occurrence that no longer name covers.
    """
    lowered = text.lower()
    spans: dict[str, list[tuple[int, int]]] = {}
    for geography in plan.candidate_geographies:
        short = geography.display_name.split(",")[0].strip().lower()
        if not short:
            continue
        found = [
            match.span() for match in re.finditer(rf"\b{re.escape(short)}\b", lowered)
        ]
        if found:
            spans[geography.slug] = found

    named: list[str] = []
    for geography in plan.candidate_geographies:
        own = spans.get(geography.slug)
        if not own:
            continue
        others = [
            span
            for slug, slug_spans in spans.items()
            if slug != geography.slug
            for span in slug_spans
        ]
        uncovered = [
            span
            for span in own
            if not any(other[0] <= span[0] and span[1] <= other[1] for other in others)
        ]
        if uncovered:
            named.append(geography.slug)
    return named


def parse_revision(
    message: str, plan: AnalysisPlanProposal, registry: MetricRegistry | None = None
) -> RevisionIntent:
    """Read a revision request into structured changes. No model involved."""
    registry = registry or get_registry()
    text = sanitize_question(message)
    intent = RevisionIntent(unsupported=detect_unsupported_dimensions(text))

    for profile in STRATEGY_PROFILES:
        stem = profile.display_name.lower().replace("-focused", "").strip()
        if stem and stem in text.lower() and re.search(
            r"\b(?:profile|lens|strateg|switch|use|apply)\b", text, re.IGNORECASE
        ):
            intent.profile_id = profile.profile_id
            return intent

    if _CONSERVATIVE.search(text) and re.search(
        r"\b(?:weight|weighting|strategy|approach)\b", text, re.IGNORECASE
    ):
        intent.reset_to_defaults = True
        return intent

    magnitude = _magnitude_for(text)
    categories = _categories_in(text)
    metrics = _metrics_in(text, registry, plan)

    # A named metric takes precedence over the category it belongs to, so "remove median
    # age" drops one metric rather than emptying the whole Customer Fit category.
    if metrics and _REMOVE.search(text):
        intent.metrics_removed = metrics
    elif magnitude and categories:
        factor, label = magnitude
        for category in categories:
            intent.weight_changes[category] = (factor, label)

    regions = _regions_in(text, plan)
    if regions and _ONLY.search(text) and len(regions) >= 2:
        intent.regions = regions
    elif regions and _REMOVE.search(text) and not metrics:
        remaining = [
            geography.slug
            for geography in plan.candidate_geographies
            if geography.slug not in regions
        ]
        if len(remaining) >= 2:
            intent.regions = remaining
    elif _ADD.search(text):
        added = _added_regions(text, plan)
        if added:
            intent.regions = [
                *[geography.slug for geography in plan.candidate_geographies],
                *added,
            ]

    return intent


def _added_regions(text: str, plan: AnalysisPlanProposal) -> list[str]:
    """Regions named in an 'add X' request, resolved through the allowlist only."""
    existing = {geography.slug for geography in plan.candidate_geographies}
    added: list[str] = []
    for candidate in re.split(r"[,\band\b]+", text.lower()):
        cleaned = _ADD.sub("", candidate).strip(" .;:").strip()
        if len(cleaned) < 3:
            continue
        try:
            geography = resolve_geography(cleaned)
        except UnsupportedGeographyError:
            continue
        if geography.slug not in existing and geography.slug not in added:
            added.append(geography.slug)
    return added


def _apply_intent(
    plan: AnalysisPlanProposal, intent: RevisionIntent
) -> tuple[dict, list[str]]:
    """Compute the proposed field values. Pure: nothing is mutated."""
    proposed: dict = {}
    changed: list[str] = []

    if intent.profile_id:
        profile = get_profile(intent.profile_id)
        if profile is not None:
            proposed["category_weights"] = dict(profile.category_weights)
            changed.append("category_weights")
    elif intent.reset_to_defaults:
        from scoring.service import DEFAULT_CATEGORY_WEIGHTS

        proposed["category_weights"] = dict(DEFAULT_CATEGORY_WEIGHTS)
        changed.append("category_weights")
    elif intent.weight_changes:
        weights = dict(plan.category_weights)
        for category, (factor, _) in intent.weight_changes.items():
            weights[category] = weights.get(category, 0.0) * factor
        total = sum(weights.values())
        if total > 0:
            weights = {category: weight / total for category, weight in weights.items()}
            proposed["category_weights"] = weights
            changed.append("category_weights")

    if intent.metrics_removed:
        remaining = [
            metric_id
            for metric_id in plan.selected_metric_ids
            if metric_id not in intent.metrics_removed
        ]
        if remaining:
            proposed["selected_metric_ids"] = remaining
            changed.append("selected_metric_ids")

    if intent.regions is not None:
        from orchestration.intent import resolve_candidate_geographies

        resolved, _ = resolve_candidate_geographies(intent.regions)
        if resolved:
            proposed["candidate_geographies"] = resolved
            changed.append("candidate_geographies")

    return proposed, changed


def _describe_effect(
    intent: RevisionIntent, plan: AnalysisPlanProposal, registry: MetricRegistry
) -> str:
    """Directional, hedged, and explicit that only a rerun settles it."""
    parts: list[str] = []

    for category, (_, label) in intent.weight_changes.items():
        members = [
            metric.display_name
            for metric in registry.by_category(category)
            if metric.metric_id in plan.selected_metric_ids
        ]
        parts.append(
            f"{CATEGORY_LABELS[category]} is {label}, which shifts the score toward "
            "regions that do well on "
            + (", ".join(members) if members else "that category")
            + "."
        )

    if intent.metrics_removed:
        names = [
            (registry.get(metric_id).display_name if registry.get(metric_id) else metric_id)
            for metric_id in intent.metrics_removed
        ]
        parts.append(
            ", ".join(names)
            + " would no longer contribute, and the remaining weights in its category "
            "would be renormalized."
        )

    if intent.regions is not None:
        parts.append(
            "Changing the candidate set changes what every metric is normalized against, "
            "so all the scores move even for regions that stayed."
        )

    if intent.profile_id:
        profile = get_profile(intent.profile_id)
        if profile:
            parts.append(f"{profile.display_name}: {profile.description}")

    if intent.reset_to_defaults:
        parts.append(
            "The documented default weights would apply, with no category emphasised."
        )

    parts.append(
        "Whether the ranking actually changes is settled by rerunning the deterministic "
        "score, not by this description."
    )
    return " ".join(parts)


def propose_revision(
    message: str,
    plan: AnalysisPlanProposal,
    registry: MetricRegistry | None = None,
) -> PlanRevisionProposal | None:
    """Build a validated, unconfirmed revision proposal, or ``None`` if nothing parsed."""
    registry = registry or get_registry()
    intent = parse_revision(message, plan, registry)

    unsupported_parts = [
        f"'{dimension}' cannot be added to the analysis: no approved metric measures it."
        for dimension in intent.unsupported
    ]

    if intent.is_empty:
        if unsupported_parts:
            return PlanRevisionProposal(
                parent_plan_id=plan.plan_id,
                parent_version=plan.version,
                requested_change=sanitize_question(message),
                rationale=(
                    "The request asks for something the analysis cannot include, so there "
                    "is no change to propose."
                ),
                unsupported_parts=unsupported_parts,
                requires_confirmation=False,
            )
        return None

    proposed, changed = _apply_intent(plan, intent)
    if not changed:
        return None

    candidate = validate_plan(plan.model_copy(update=proposed), registry)

    before_values = {}
    proposed_values = {}
    for field_name in changed:
        if field_name == "candidate_geographies":
            before_values[field_name] = [
                geography.display_name for geography in plan.candidate_geographies
            ]
            proposed_values[field_name] = [
                geography.display_name for geography in candidate.candidate_geographies
            ]
        elif field_name == "category_weights":
            before_values[field_name] = {
                str(category): round(weight, 4)
                for category, weight in plan.category_weights.items()
            }
            proposed_values[field_name] = {
                str(category): round(weight, 4)
                for category, weight in candidate.category_weights.items()
            }
        else:
            before_values[field_name] = getattr(plan, field_name)
            proposed_values[field_name] = getattr(candidate, field_name)

    return PlanRevisionProposal(
        parent_plan_id=plan.plan_id,
        parent_version=plan.version,
        requested_change=sanitize_question(message),
        changed_fields=changed,
        before_values=before_values,
        proposed_values=proposed_values,
        rationale=_revision_rationale(intent, registry),
        expected_effect=_describe_effect(intent, plan, registry),
        validation=candidate.validation,
        requires_confirmation=True,
        unsupported_parts=unsupported_parts,
    )


def _revision_rationale(intent: RevisionIntent, registry: MetricRegistry) -> str:
    if intent.profile_id:
        profile = get_profile(intent.profile_id)
        return f"Read as a request to apply the {profile.display_name} weighting lens."
    if intent.reset_to_defaults:
        return "Read as a request to return to the documented default weights."

    parts: list[str] = []
    for category, (factor, label) in intent.weight_changes.items():
        parts.append(
            f"have the weight on {CATEGORY_LABELS[category]} {label}, at {factor:g}x its "
            "current value, with all five category weights then renormalized to sum to 1"
        )
    if intent.metrics_removed:
        names = [
            (registry.get(metric_id).display_name if registry.get(metric_id) else metric_id)
            for metric_id in intent.metrics_removed
        ]
        parts.append("drop " + ", ".join(names) + " from the metric set")
    if intent.regions is not None:
        parts.append("change which regions are being compared")

    return "Read as a request to " + ", and to ".join(parts) + "."


def apply_revision(
    plan: AnalysisPlanProposal,
    revision: PlanRevisionProposal,
    registry: MetricRegistry | None = None,
    note: str | None = None,
) -> AnalysisPlanProposal:
    """Create the next plan version from a confirmed revision.

    The parent is not modified. The caller is expected to mark it superseded once the new
    version executes, which keeps the prior result available for comparison.
    """
    registry = registry or get_registry()
    if revision.parent_plan_id != plan.plan_id:
        raise ValueError(
            f"Revision {revision.revision_id} belongs to plan {revision.parent_plan_id}, "
            f"not {plan.plan_id}."
        )
    if not revision.is_actionable:
        raise ValueError(
            f"Revision {revision.revision_id} has nothing to apply, or did not pass "
            "deterministic validation."
        )

    update: dict = {
        "version": plan.version + 1,
        "parent_plan_id": plan.plan_id,
        "revision_summary": revision.requested_change,
        "status": PlanStatus.DRAFT,
        "approval_record": ApprovalRecord(),
    }

    for field_name in revision.changed_fields:
        if field_name == "category_weights":
            update["category_weights"] = {
                MetricCategory(key): value
                for key, value in revision.proposed_values["category_weights"].items()
            }
        elif field_name == "candidate_geographies":
            from orchestration.intent import resolve_candidate_geographies

            resolved, _ = resolve_candidate_geographies(
                revision.proposed_values["candidate_geographies"]
            )
            update["candidate_geographies"] = resolved
        else:
            update[field_name] = revision.proposed_values[field_name]

    revised = plan.model_copy(update=update)
    return validate_plan(revised, registry)
