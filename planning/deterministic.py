"""The deterministic planner.

The language-model planner is an upgrade to language understanding, not a runtime
dependency. Everything the product does must remain available with no key configured, so
this module builds a complete, honest plan from pattern matching alone: it reads priority
phrases, maps them onto scoring categories, applies a documented weighting rule, notices
what the objective did not say, and asks for the small number of things that would
actually change the analysis.

It is deliberately conservative. Where the LLM planner may interpret an unusual phrasing,
this one prefers to leave a field :attr:`Provenance.UNKNOWN` and attach a question. An
unanswered question with a disclosed default is a worse experience than a correct
inference and a much better one than a confident guess.

The weighting rule, stated once so the UI and the docs can quote it:

* Start from the documented default category weights.
* A category named as a priority is multiplied by :data:`PRIORITY_BOOST`.
* A category named as explicitly less important is multiplied by :data:`DEPRIORITY_FACTOR`.
* The result is renormalized to sum to 1.

Nothing about that rule is learned or tuned. It is a transparent encoding of emphasis, and
the reviewer can overwrite every number it produces before anything runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from metrics.registry import MetricRegistry, get_registry
from models.metrics import CATEGORY_LABELS, MetricCategory
from models.plan import (
    AnalysisPlanProposal,
    Assumption,
    ClarificationQuestion,
    PlannerProvenance,
    UnsupportedRequirement,
)
from models.strategy import Attributed, RetailStrategyProfile
from orchestration.intent import (
    detect_unsupported_dimensions,
    resolve_candidate_geographies,
    sanitize_question,
)
from planning.capabilities import CapabilityRegistry, get_capability_registry
from scoring.service import DEFAULT_CATEGORY_WEIGHTS, ScoringService

PRIORITY_BOOST = 2.0
DEPRIORITY_FACTOR = 0.5

MAX_QUESTIONS_PER_ROUND = 3

# Phrases that name a scoring category in ordinary retail language. Matching is on the
# objective text only; nothing here reads a value or an Atlas identifier.
_CATEGORY_PHRASES: dict[MetricCategory, tuple[str, ...]] = {
    MetricCategory.MARKET_POTENTIAL: (
        "market size", "current market size", "population size", "sheer size", "scale",
        "volume", "reach", "customer base", "catchment size", "how many people",
        "big market", "large market", "market potential", "headcount",
    ),
    MetricCategory.CUSTOMER_FIT: (
        "customer fit", "demographic", "demographics", "target customer", "segment",
        "students", "student", "campus", "young", "youth", "families", "family",
        "age profile", "education", "educated", "who lives", "right shopper",
        "target shopper",
    ),
    MetricCategory.ECONOMIC_ATTRACTIVENESS: (
        "income", "purchasing power", "affluent", "affluence", "wealth", "wealthy",
        "spend", "spending power", "disposable", "premium", "high-end", "upmarket",
        "employment", "economic", "able to afford", "middle-income", "middle income",
    ),
    MetricCategory.ACCESSIBILITY: (
        "accessib", "accessible", "commute", "commuting", "transport", "transit",
        "drive time", "drive-time", "easy to reach", "convenience", "convenient",
        "getting there", "travel time",
    ),
    MetricCategory.GROWTH_OUTLOOK: (
        "growth", "growing", "grow", "trajectory", "future", "expansion", "expanding",
        "trend", "trending", "momentum", "long term", "long-term", "where it is heading",
        "upside", "emerging",
    ),
}

# Splits an objective into what the user wants emphasised and what they explicitly rank
# below it: "prioritize growth and accessibility over current market size".
_DEPRIORITY_SPLIT = re.compile(
    r"\b(?:over|rather than|instead of|ahead of|more than|not)\b", re.IGNORECASE
)

# Priority markers, grouped by where the category sits relative to the marker. "Prioritize
# growth" names the category after; "growth is the priority" names it before. Both are
# ordinary ways for an executive to write, and reading only one of them would silently
# ignore half of them.
_PRIORITY_CLAUSE = re.compile(
    r"\b(?:prioriti[sz]e|focus(?:ing|ed)? on|emphasi[sz]e|weight(?:ed)? toward|"
    r"lean(?:ing)? toward|care (?:most )?about|optimi[sz]e for|favou?r|led by|driven by)\b",
    re.IGNORECASE,
)

_TRAILING_PRIORITY = re.compile(
    r"\b(?:(?:is|are)\s+(?:the\s+)?(?:top\s+|main\s+|number one\s+)?priority|"
    r"matters?\s+most|(?:is|are)\s+most\s+important|comes?\s+first|"
    r"(?:is|are)\s+the\s+(?:key|main|primary)\s+(?:driver|factor|consideration))\b",
    re.IGNORECASE,
)

_LEADING_DEMOTION = re.compile(
    r"\b(?:de-?prioriti[sz]e|de-?emphasi[sz]e|care less about|downweight|"
    r"less concerned (?:about|with)|not (?:very )?(?:worried|concerned) about)\b",
    re.IGNORECASE,
)

_TRAILING_DEMOTION = re.compile(
    r"\b(?:matters?\s+(?:less|least)|(?:is|are)\s+less\s+important|"
    r"(?:is|are)\s+secondary|(?:is|are)\s+a\s+lower\s+priority|weighs?\s+less)\b",
    re.IGNORECASE,
)

_FORMAT_PHRASES: dict[str, tuple[str, ...]] = {
    "suburban": ("suburban", "suburb", "out of town", "out-of-town"),
    "urban": ("urban", "downtown", "city centre", "city center", "high street", "flagship"),
    "outlet": ("outlet", "off-price", "off price", "clearance"),
    "mall": ("mall", "shopping centre", "shopping center"),
    "pop-up": ("pop-up", "pop up", "temporary", "seasonal"),
}

_SEGMENT_PHRASES: tuple[str, ...] = (
    "middle-income families", "middle income families", "families", "students",
    "young professionals", "young adults", "commuters", "seniors", "teenagers",
    "affluent households", "value shoppers",
)


@dataclass
class PlanningRequest:
    """Everything the user has told us, before any interpretation."""

    objective: str
    geographies: list[str] = field(default_factory=list)
    retailer_type: str | None = None
    store_format: str | None = None
    target_segments: str | None = None
    answers: dict[str, str] = field(default_factory=dict)
    category_weights: dict[MetricCategory, float] | None = None
    """Set when a human has already edited the weights; suppresses the priority rule."""

    metric_ids: list[str] | None = None
    parent_plan_id: str | None = None
    version: int = 1
    revision_summary: str | None = None


def _whole_word_at(text: str, start: int, length: int) -> str:
    """Return the match extended to its word ending, for quoting back to the user.

    Several category phrases are stems, so that "accessible" and "accessibility" both
    match one entry. Quoting the stem in an assumption an executive reads would show them
    "accessib", which looks like a bug rather than a reading of their own sentence.
    """
    end = start + length
    while end < len(text) and (text[end].isalnum() or text[end] == "-"):
        end += 1
    return text[start:end]


@dataclass
class PriorityReading:
    priorities: list[MetricCategory]
    secondary: list[MetricCategory]
    matched_phrases: dict[MetricCategory, str]


def read_priorities(objective: str) -> PriorityReading:
    """Work out which categories the objective emphasises, and which it ranks below them.

    A priority marker has a direction and a scope. "Prioritize growth" puts the category
    *after* the marker; "purchasing power is the priority" puts it *before*. Both forms are
    read, clause by clause.

    When any clause states a priority explicitly, only the marked clauses vote. Otherwise
    every descriptive phrase in the objective would vote too, and "a suburban store for
    middle-income families, prioritize growth" would quietly raise Customer Fit and
    Economic Attractiveness off a description of the customer, drowning out the one
    priority the user actually stated.

    With no marker anywhere, the whole objective is read as emphasis. That is the right
    default: the user described what they care about without ranking it.
    """
    lowered = objective.lower()
    matched: dict[MetricCategory, str] = {}

    def categories_in(text: str) -> list[MetricCategory]:
        found: list[MetricCategory] = []
        for category, phrases in _CATEGORY_PHRASES.items():
            for phrase in phrases:
                at = text.find(phrase)
                if at >= 0:
                    if category not in matched:
                        matched[category] = _whole_word_at(text, at, len(phrase))
                    if category not in found:
                        found.append(category)
                    break
        return found

    promoted: list[MetricCategory] = []
    demoted: list[MetricCategory] = []
    saw_marker = False

    for clause in re.split(r"[.;]|,\s+(?:and|but)\s+", lowered):
        if not clause.strip():
            continue

        ranking = _DEPRIORITY_SPLIT.search(clause)
        leading_up = _PRIORITY_CLAUSE.search(clause)
        trailing_up = _TRAILING_PRIORITY.search(clause)
        leading_down = _LEADING_DEMOTION.search(clause)
        trailing_down = _TRAILING_DEMOTION.search(clause)

        if ranking:
            saw_marker = True
            above, below = clause[: ranking.start()], clause[ranking.end() :]
            if leading_up and leading_up.end() <= ranking.start():
                above = above[leading_up.end() :]
            promoted += categories_in(above)
            demoted += categories_in(below)
        elif leading_up:
            saw_marker = True
            promoted += categories_in(clause[leading_up.end() :])
        elif trailing_up:
            saw_marker = True
            promoted += categories_in(clause[: trailing_up.start()])
        elif leading_down:
            saw_marker = True
            demoted += categories_in(clause[leading_down.end() :])
        elif trailing_down:
            saw_marker = True
            demoted += categories_in(clause[: trailing_down.start()])

    if not saw_marker:
        promoted = categories_in(lowered)

    demoted = list(dict.fromkeys(demoted))
    promoted = [
        category
        for category in dict.fromkeys(promoted)
        if category not in demoted
    ]
    return PriorityReading(priorities=promoted, secondary=demoted, matched_phrases=matched)


def weights_for(reading: PriorityReading) -> tuple[dict[MetricCategory, float], list[str]]:
    """Apply the documented emphasis rule and describe what it did."""
    weights = dict(DEFAULT_CATEGORY_WEIGHTS)
    notes: list[str] = []

    for category in reading.priorities:
        weights[category] = weights[category] * PRIORITY_BOOST
        notes.append(
            f"{CATEGORY_LABELS[category]} was raised because the objective named it as a "
            f"priority (\"{reading.matched_phrases[category]}\")."
        )
    for category in reading.secondary:
        weights[category] = weights[category] * DEPRIORITY_FACTOR
        notes.append(
            f"{CATEGORY_LABELS[category]} was lowered because the objective ranked it "
            f"below the priorities (\"{reading.matched_phrases[category]}\")."
        )

    total = sum(weights.values())
    weights = {category: weight / total for category, weight in weights.items()}
    return weights, notes


def _detect_format(text: str) -> str | None:
    lowered = text.lower()
    for label, phrases in _FORMAT_PHRASES.items():
        if any(phrase in lowered for phrase in phrases):
            return label
    return None


def _detect_segments(text: str) -> list[str]:
    lowered = text.lower()
    found = [phrase for phrase in _SEGMENT_PHRASES if phrase in lowered]
    # "middle-income families" also contains "families"; keep the more specific phrase.
    return [
        phrase
        for phrase in found
        if not any(other != phrase and phrase in other for other in found)
    ]


def build_profile(
    request: PlanningRequest, reading: PriorityReading, unsupported: list[str]
) -> RetailStrategyProfile:
    """Assemble the strategy profile, tagging every field with where it came from."""
    objective = request.objective
    answers = request.answers

    retailer_type = (
        Attributed[str].from_user(request.retailer_type)
        if request.retailer_type
        else Attributed[str].inferred(
            "Mainstream apparel retailer",
            "No retailer type was stated. The prototype's illustrative scenario is a "
            "national mainstream apparel banner; this only affects the wording of the "
            "narrative, not the metrics or the score.",
        )
    )

    format_answer = answers.get("store_format") or request.store_format
    detected_format = _detect_format(objective)
    if format_answer:
        store_format = Attributed[str].from_user(format_answer)
    elif detected_format:
        store_format = Attributed[str].inferred(
            detected_format,
            f"The objective described the store as {detected_format!r}.",
        )
    else:
        store_format = Attributed[str].unknown(
            "Format drives how heavily purchasing power should be weighted: an outlet "
            "and a full-price store want different income profiles."
        )

    segment_answer = answers.get("target_customer") or request.target_segments
    detected_segments = _detect_segments(objective)
    if segment_answer:
        segments = Attributed[list[str]].from_user([segment_answer])
    elif detected_segments:
        segments = Attributed[list[str]].from_user(detected_segments)
    else:
        segments = Attributed[list[str]].unknown(
            "Without a target segment the customer-fit metrics are weighted for a broad "
            "mainstream shopper, which suits few specific banners."
        )

    priorities = (
        Attributed[list[str]].from_user(
            [CATEGORY_LABELS[category] for category in reading.priorities]
        )
        if reading.priorities
        else Attributed[list[str]].unknown(
            "No priority was stated, so the documented default weights are used and no "
            "category is emphasised over another."
        )
    )
    secondary = (
        Attributed[list[str]].from_user(
            [CATEGORY_LABELS[category] for category in reading.secondary]
        )
        if reading.secondary
        else Attributed[list[str]].unknown()
    )

    trade_area_answer = answers.get("trade_area")
    trade_area = (
        Attributed[str].from_user(trade_area_answer)
        if trade_area_answer
        else Attributed[str].unknown(
            "The analysis compares whole municipalities or counties. A real catchment is "
            "a drive-time area, which the system cannot construct."
        )
    )

    return RetailStrategyProfile(
        retailer_type=retailer_type,
        store_format=store_format,
        target_customer_segments=segments,
        strategic_priorities=priorities,
        secondary_priorities=secondary,
        hard_constraints=Attributed[list[str]].unknown(),
        preferred_market_type=(
            Attributed[str].inferred(
                detected_format,
                f"Read from the objective's description of a {detected_format} store.",
            )
            if detected_format
            else Attributed[str].unknown()
        ),
        trade_area_definition=trade_area,
        risk_tolerance=Attributed[str].unknown(),
        requested_dimensions=(
            Attributed[list[str]].unsupported(
                unsupported,
                "These were asked for and no approved metric can express them.",
            )
            if unsupported
            else Attributed[list[str]].unknown()
        ),
        notes=None,
    )


def build_questions(
    request: PlanningRequest,
    profile: RetailStrategyProfile,
    resolved_count: int,
    rejected: list[str],
) -> list[ClarificationQuestion]:
    """Ask only what could change the analysis, and never more than three at a time."""
    answers = request.answers
    candidates: list[ClarificationQuestion] = []

    if resolved_count < 2:
        detail = (
            f"{len(rejected)} named region(s) could not be matched to the licensed "
            "footprint: " + ", ".join(rejected) + "."
            if rejected
            else "The objective did not name two or more comparable regions."
        )
        candidates.append(
            ClarificationQuestion(
                question_id="candidate_regions",
                question=(
                    "Which regions should I compare? I need at least two from the "
                    "licensed footprint."
                ),
                missing_decision="The candidate set itself",
                why_it_matters=(
                    f"{detail} There is nothing to compare until two regions resolve, and "
                    "I will not choose candidates on your behalf."
                ),
                affects=["Whether the analysis can run at all", "Every metric value"],
                required=True,
            )
        )

    if not profile.store_format.is_known and "store_format" not in answers:
        candidates.append(
            ClarificationQuestion(
                question_id="store_format",
                question=(
                    "Is this a suburban full-price store, an outlet, or an urban format?"
                ),
                missing_decision="Store format",
                why_it_matters=(
                    "An outlet wants a different income profile than a full-price store, "
                    "and an urban format leans on density and student population rather "
                    "than household count."
                ),
                affects=[
                    "Economic Attractiveness weight",
                    "Customer Fit weight",
                    "How median age is interpreted",
                ],
                required=False,
                safe_default=(
                    "Treat it as a mainstream full-price format and use the default "
                    "category weights."
                ),
            )
        )

    if not profile.strategic_priorities.is_known and "priority_balance" not in answers:
        candidates.append(
            ClarificationQuestion(
                question_id="priority_balance",
                question=(
                    "Should the comparison favour today's purchasing power or future "
                    "population growth?"
                ),
                missing_decision="Where the emphasis sits between current and future",
                why_it_matters=(
                    "These pull in opposite directions here, and the leader can change "
                    "depending on which one carries more weight."
                ),
                affects=["Economic Attractiveness weight", "Growth Outlook weight"],
                required=False,
                safe_default="Use the documented default weights, which balance the two.",
            )
        )

    if not profile.trade_area_definition.is_known and "trade_area" not in answers:
        candidates.append(
            ClarificationQuestion(
                question_id="trade_area",
                question=(
                    "Should each municipality be treated as the market, or would you "
                    "ultimately use drive-time trade areas?"
                ),
                missing_decision="Trade-area definition",
                why_it_matters=(
                    "Administrative boundaries rarely match a real catchment. Knowing you "
                    "intend drive-time areas does not change what I can compute, but it "
                    "changes how much weight the result should carry."
                ),
                affects=["How the geography is interpreted", "The caveats on the result"],
                required=False,
                safe_default="Treat each named municipality or county as the market.",
            )
        )

    answered = [
        question.model_copy(update={"answer": answers[question.question_id]})
        if question.question_id in answers
        else question
        for question in candidates
    ]
    return answered[:MAX_QUESTIONS_PER_ROUND]


def build_unsupported(
    dimensions: list[str], capabilities: CapabilityRegistry
) -> list[UnsupportedRequirement]:
    requirements: list[UnsupportedRequirement] = []
    for dimension in dimensions:
        capability = capabilities.for_requirement(dimension)
        requirements.append(
            UnsupportedRequirement(
                requirement=dimension,
                why_unavailable=(
                    capability.unavailable_because
                    if capability and capability.unavailable_because
                    else (
                        "The StateBook Atlas API describes geographic areas using public "
                        "statistical sources and carries nothing on this."
                    )
                ),
                would_require=(
                    ", ".join(capability.required_data)
                    if capability and capability.required_data
                    else "A commercial data source outside Atlas."
                )
                + (
                    f" Expected provider: {capability.expected_provider}."
                    if capability and capability.expected_provider
                    else ""
                ),
                capability_id=capability.capability_id if capability else None,
            )
        )
    return requirements


def _assumptions_from(
    profile: RetailStrategyProfile,
    questions: list[ClarificationQuestion],
    weight_notes: list[str],
    used_default_weights: bool,
) -> list[Assumption]:
    assumptions: list[Assumption] = []

    for name, attributed in profile.assumptions().items():
        assumptions.append(
            Assumption(
                subject=name,
                assumption=attributed.describe(),
                basis=attributed.note or "",
                reversible_by="Edit the strategy profile before approving the plan.",
            )
        )

    # An optional question left unanswered proceeds on its stated default. That default
    # is recorded here as an assumption so it is visible in the plan, rather than being
    # applied silently because nobody clicked on it.
    for question in questions:
        if not question.required and not question.answered and question.safe_default:
            assumptions.append(
                Assumption(
                    subject=question.missing_decision,
                    assumption=question.safe_default,
                    basis=(
                        f"You have not answered: \"{question.question}\" The analysis "
                        "proceeds on this default and discloses it."
                    ),
                    reversible_by="Answer the question and regenerate the plan.",
                )
            )

    for note in weight_notes:
        assumptions.append(
            Assumption(
                subject="Category weighting",
                assumption=note,
                basis=(
                    f"Priority phrases raise a category by {PRIORITY_BOOST:g}x and "
                    f"explicitly deprioritised ones by {DEPRIORITY_FACTOR:g}x, before "
                    "renormalizing to sum to 1."
                ),
                reversible_by="Edit the category weights before approving the plan.",
            )
        )

    if used_default_weights:
        assumptions.append(
            Assumption(
                subject="Category weighting",
                assumption="The documented default category weights were used unchanged.",
                basis="No priority was detected in the objective.",
                reversible_by="Edit the category weights before approving the plan.",
            )
        )

    return assumptions


def _expected_outputs(region_count: int) -> list[str]:
    return [
        f"A ranked comparison of {region_count} candidate region(s) on a 0-100 score.",
        "A score per category, showing which part of the strategy each region satisfies.",
        "Every raw value with its Atlas datapoint identifier, source, period, and geography.",
        "An explicit list of metrics that were excluded, and why.",
        "A narrative whose every figure is verified against the retrieved evidence.",
        "A reproducibility hash covering the regions, weights, metrics, and observations.",
    ]


def _evidence_requirements() -> list[str]:
    return [
        "Every value must come from a live StateBook Atlas response; nothing is estimated.",
        (
            f"At least {ScoringService.MIN_METRICS_FOR_RANKING} metrics must survive "
            "validation, or the ranking is withheld."
        ),
        "At least two regions must produce a score, or there is nothing to rank.",
        (
            f"The top two regions must be separated by more than "
            f"{ScoringService.MIN_SCORE_MARGIN:g} points, and by more than "
            f"{ScoringService.MIN_RAW_SEPARATION:.0%} in the underlying raw values."
        ),
        "Values must share a period, a source, a unit, and a geographic resolution.",
    ]


def build_deterministic_plan(
    request: PlanningRequest,
    registry: MetricRegistry | None = None,
    capabilities: CapabilityRegistry | None = None,
) -> AnalysisPlanProposal:
    """Construct a complete plan proposal with no model involvement."""
    registry = registry or get_registry()
    capabilities = capabilities or get_capability_registry()

    sanitized = sanitize_question(request.objective)
    resolved, rejected = resolve_candidate_geographies(request.geographies)

    reading = read_priorities(sanitized)
    unsupported_dimensions = detect_unsupported_dimensions(sanitized)
    profile = build_profile(request, reading, unsupported_dimensions)
    questions = build_questions(request, profile, len(resolved), rejected)

    if request.category_weights:
        weights = dict(request.category_weights)
        weight_notes: list[str] = []
        used_defaults = False
    else:
        weights, weight_notes = weights_for(reading)
        used_defaults = not reading.priorities and not reading.secondary

    metric_ids = _select_metric_ids(request, registry, resolved)

    excluded: list[str] = []
    if rejected:
        excluded.append(
            "Regions outside the licensed footprint were dropped from the candidate set: "
            + ", ".join(rejected)
            + "."
        )

    rationale = _rationale(reading, resolved, metric_ids, unsupported_dimensions)

    return AnalysisPlanProposal(
        version=request.version,
        parent_plan_id=request.parent_plan_id,
        revision_summary=request.revision_summary,
        original_request=request.objective,
        sanitized_request=sanitized,
        retail_strategy_profile=profile,
        candidate_geographies=resolved,
        selected_metric_ids=metric_ids,
        category_weights=weights,
        assumptions=_assumptions_from(profile, questions, weight_notes, used_defaults),
        clarification_questions=questions,
        unsupported_requirements=build_unsupported(unsupported_dimensions, capabilities),
        excluded_requirements=excluded,
        planner_rationale=rationale,
        expected_outputs=_expected_outputs(len(resolved)),
        evidence_requirements=_evidence_requirements(),
        planner_provenance=PlannerProvenance(planner="deterministic"),
    )


def _select_metric_ids(
    request: PlanningRequest, registry: MetricRegistry, resolved
) -> list[str]:
    """Take every registry metric published at all candidate levels.

    Breadth is the conservative choice: a wider base makes any single metric less able to
    swing the ranking, and the weighting - not the selection - is where emphasis belongs.
    """
    if request.metric_ids:
        return [metric_id for metric_id in request.metric_ids if metric_id in registry]

    if not resolved:
        return [metric.metric_id for metric in registry.all()]

    types = [geography.geography_type for geography in resolved]
    return [
        metric.metric_id
        for metric in registry.all()
        if all(metric.supports(level) for level in types)
    ]


def _rationale(
    reading: PriorityReading,
    resolved,
    metric_ids: list[str],
    unsupported: list[str],
) -> str:
    parts = [
        f"Compare {len(resolved)} candidate region(s) on {len(metric_ids)} verified Atlas "
        "metric(s), scoring each against five retail categories."
    ]
    if reading.priorities:
        parts.append(
            "The objective emphasised "
            + ", ".join(CATEGORY_LABELS[category] for category in reading.priorities)
            + ", so those categories carry more weight."
        )
    if reading.secondary:
        parts.append(
            "It ranked "
            + ", ".join(CATEGORY_LABELS[category] for category in reading.secondary)
            + " below those, so they carry less."
        )
    if not reading.priorities and not reading.secondary:
        parts.append(
            "No priority was stated, so the documented default weights apply unchanged."
        )
    if unsupported:
        parts.append(
            "It also asked about "
            + ", ".join(unsupported)
            + ", which no approved metric can express. Those are listed as unsupported "
            "rather than approximated."
        )
    parts.append(
        "This plan was generated deterministically by pattern matching, with no language "
        "model involved."
    )
    return " ".join(parts)
