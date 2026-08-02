"""Intent layer: turn a business question into a structured, constrained analysis plan.

This layer is deliberately the least trusted component in the system. It reads untrusted
text, so it is given the narrowest possible authority: it may pick geographies from an
allowlist and metric ids from the registry, and nothing else. It cannot emit a datapoint
identifier, a value, a period, or a score. Everything it produces is re-validated by the
caller before a single API call is made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from api.geographies import UnsupportedGeographyError, resolve_geography
from metrics.registry import MetricRegistry
from models.analysis import Refusal
from models.geography import Geography
from models.metrics import MetricCategory

MAX_QUESTION_LENGTH = 2000


class RefusalKind(StrEnum):
    COMPANY_SPECIFIC_FORECAST = "company_specific_forecast"
    UNSUPPORTED_DIMENSION = "unsupported_dimension"
    PROMPT_INJECTION = "prompt_injection"
    INSUFFICIENT_GEOGRAPHIES = "insufficient_geographies"
    UNSUPPORTED_GEOGRAPHY = "unsupported_geography"


# Phrases that indicate the user is asking for a financial projection about a specific
# business. Atlas describes a market; it cannot describe a company's economics in it.
_FORECAST_PATTERNS = [
    r"\broi\b",
    r"\breturn on investment\b",
    r"\bpayback\b",
    r"\bbreak[- ]?even\b",
    r"\bprofit(?:ability|able)?\b",
    r"\brevenue\b",
    r"\bsales (?:forecast|projection|volume|per square)\b",
    r"\bnet present value\b|\bnpv\b",
    r"\birr\b",
    r"\bforecast\b.*\b(sales|revenue|profit|earnings)\b",
    r"\b(one|two|three|four|five|ten|\d+)[- ]year\b.*\b(roi|return|profit|revenue|forecast|projection)\b",
    r"\bhow much (?:money|revenue|profit)\b",
    r"\bwill (?:we|it|the store) make\b",
]

# Retail dimensions a real site-selection decision needs that Atlas does not carry.
_UNSUPPORTED_DIMENSIONS: dict[str, str] = {
    "foot traffic": "pedestrian or vehicle counts at candidate sites",
    "footfall": "pedestrian or vehicle counts at candidate sites",
    "competitor": "competitor store locations and formats",
    "competition": "competitor store locations and formats",
    "cannibalization": "the retailer's own store network and overlapping trade areas",
    "cannibalisation": "the retailer's own store network and overlapping trade areas",
    "rent": "site-level lease and occupancy costs",
    "lease": "site-level lease and occupancy costs",
    "construction cost": "build-out and construction cost estimates",
    "gross margin": "category-level gross margin assumptions",
    "supply chain": "distribution-network and freight cost modelling",
    "loyalty": "the retailer's customer transaction and loyalty data",
    "transaction data": "the retailer's customer transaction and loyalty data",
    "market share": "competitor revenue and category share data",
}

# Attempts to talk the agent out of its evidence requirements.
_INJECTION_PATTERNS = [
    r"ignore (?:all |any |the )?(?:previous|prior|above|earlier) instructions?",
    r"disregard (?:all |any |the )?(?:previous|prior|above|your) (?:instructions?|rules?|constraints?)",
    r"you are now\b",
    r"act as (?:if|though|a)\b.*\b(?:no|without) (?:restrictions?|limits?|rules?)",
    r"(?:make up|invent|fabricate|hallucinate|guess|estimate)\s+(?:the |some |any |a )?(?:numbers?|data|values?|figures?|statistics?)",
    r"without (?:citing|citations?|evidence|sources?|data)",
    r"(?:skip|bypass|disable|turn off|override)\s+(?:the )?(?:validation|verification|guardrails?|checks?|safety|evidence)",
    r"pretend (?:that )?(?:you|the data)\b",
    r"just (?:say|tell me|answer)\b.*\b(?:anyway|regardless|even if)",
    r"do not (?:mention|include|show)\s+(?:the )?(?:limitations?|caveats?|missing|uncertainty)",
    r"reveal (?:your|the) (?:system )?prompt",
    r"(?:print|show|output|give|tell)\s+(?:me\s+)?(?:your |the )?(?:api[_ ]?key|auth token|token|credentials?|secret)",
]

_COMPILED_FORECAST = [re.compile(pattern, re.IGNORECASE) for pattern in _FORECAST_PATTERNS]
_COMPILED_INJECTION = [re.compile(pattern, re.IGNORECASE) for pattern in _INJECTION_PATTERNS]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class IntentResult:
    """Outcome of interpreting a question. Exactly one of ``plan_ok`` / ``refusal`` holds."""

    sanitized_question: str
    plan_ok: bool
    refusal: Refusal | None = None
    refusal_kind: RefusalKind | None = None
    notes: list[str] = field(default_factory=list)
    flagged_injection: bool = False


def sanitize_question(raw: str) -> str:
    """Strip control characters and cap length before the text touches anything else."""
    text = _CONTROL_CHARS.sub(" ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_QUESTION_LENGTH]


def detect_injection(question: str) -> list[str]:
    return [pattern.pattern for pattern in _COMPILED_INJECTION if pattern.search(question)]


def detect_forecast_request(question: str) -> bool:
    return any(pattern.search(question) for pattern in _COMPILED_FORECAST)


def detect_unsupported_dimensions(question: str) -> list[str]:
    lowered = question.lower()
    return sorted(
        {
            requirement
            for phrase, requirement in _UNSUPPORTED_DIMENSIONS.items()
            if phrase in lowered
        }
    )


SUPPORTED_CAPABILITIES = [
    "Compare observable market indicators across regions licensed by the active token.",
    "Rank regions on a transparent, reproducible weighted score built only from Atlas values.",
    "Show the Atlas datapoint identifier, source, period, and geography behind every number.",
    "Disclose which indicators were unavailable or incomparable, and why.",
]


def _forecast_refusal(question: str, extra_requirements: list[str]) -> Refusal:
    requirements = [
        "Store format, footprint, and merchandising plan for each candidate site.",
        "Site-level rent, common-area charges, and build-out or construction cost.",
        "Existing store network and modelled cannibalization of overlapping trade areas.",
        "Observed foot traffic or vehicle counts at the specific sites under consideration.",
        "Competitor locations, formats, and category share in each trade area.",
        "The retailer's own customer transaction, basket, and loyalty data.",
        "Category-level gross margin and markdown assumptions.",
        "Supply-chain and distribution cost to serve each location.",
        "Marketing and launch investment assumptions.",
        "A forecasting methodology approved by the retailer's finance function.",
    ]
    for requirement in extra_requirements:
        formatted = requirement[0].upper() + requirement[1:] + "."
        if formatted not in requirements:
            requirements.append(formatted)

    return Refusal(
        question=question,
        reason=(
            "This asks for a company-specific financial projection. The StateBook Atlas API "
            "publishes observed market indicators for geographic areas; it contains no "
            "information about this retailer's economics, its stores, its customers, or its "
            "competitors. Producing a return-on-investment figure from these inputs would "
            "require inventing the majority of the model, and the resulting number would "
            "look authoritative while resting on assumptions the system cannot evidence."
        ),
        unsupported_because=[
            "Atlas describes areas, not businesses: it has no revenue, cost, or margin data.",
            "No store-level operating or site-cost inputs are available to the system.",
            "No approved forecasting methodology has been supplied or validated.",
            "Any multi-year projection would compound assumptions that cannot be traced to "
            "an API response.",
        ],
        required_inputs=requirements,
        offered_alternative=(
            "The system can instead compare the candidate regions on the observable market "
            "indicators Atlas does publish - population and household base, income and "
            "purchasing-power proxies, age and education composition, employment, commute "
            "accessibility, and growth trends - and rank them with a transparent, "
            "reproducible score in which every value is traceable to an Atlas response. "
            "That output is an input to a return-on-investment model, not a substitute for one."
        ),
        supported_capabilities=SUPPORTED_CAPABILITIES,
    )


def _injection_refusal(question: str, matched: list[str]) -> Refusal:
    return Refusal(
        question=question,
        reason=(
            "The request contains instructions that attempt to override the system's "
            "evidence requirements. Those instructions were ignored, and the request was not "
            "executed. This system reports only values returned by the StateBook Atlas API, "
            "and it cites the datapoint identifier, source, period, and geography for each "
            "one. It has no mode in which it produces numbers without that provenance."
        ),
        unsupported_because=[
            "User-supplied text is treated as data describing an analysis request, never as "
            "instructions that can change the system's rules.",
            f"{len(matched)} instruction-override pattern(s) matched in the submitted text.",
            "Factual values originate solely from validated Atlas responses; there is no "
            "code path that can generate one.",
        ],
        required_inputs=[
            "A legitimate comparison request naming two or more supported candidate regions."
        ],
        offered_alternative=(
            "Ask which of a set of supported regions looks most attractive on the verified "
            "Atlas indicators, and the system will produce a ranked, fully cited comparison."
        ),
        supported_capabilities=SUPPORTED_CAPABILITIES,
    )


def interpret_question(question: str) -> IntentResult:
    """Classify a question before any tool is selected or any API call is made."""
    sanitized = sanitize_question(question)

    if not sanitized:
        return IntentResult(
            sanitized_question=sanitized,
            plan_ok=True,
            notes=["No question text supplied; defaulting to a standard region comparison."],
        )

    matched_injection = detect_injection(sanitized)
    if matched_injection:
        return IntentResult(
            sanitized_question=sanitized,
            plan_ok=False,
            refusal=_injection_refusal(sanitized, matched_injection),
            refusal_kind=RefusalKind.PROMPT_INJECTION,
            flagged_injection=True,
            notes=[f"Blocked {len(matched_injection)} instruction-override pattern(s)."],
        )

    unsupported = detect_unsupported_dimensions(sanitized)

    if detect_forecast_request(sanitized):
        return IntentResult(
            sanitized_question=sanitized,
            plan_ok=False,
            refusal=_forecast_refusal(sanitized, unsupported),
            refusal_kind=RefusalKind.COMPANY_SPECIFIC_FORECAST,
            notes=["Question requests a company-specific financial projection."],
        )

    notes: list[str] = []
    if unsupported:
        notes.append(
            "The question references "
            + ", ".join(unsupported)
            + ", which Atlas does not provide. The comparison proceeds on the indicators "
            "that are available and this gap is reported as a limitation."
        )

    return IntentResult(sanitized_question=sanitized, plan_ok=True, notes=notes)


def resolve_candidate_geographies(
    raw_geographies: list[str],
) -> tuple[list[Geography], list[str]]:
    """Resolve user-supplied geography strings against the allowlist.

    Returns the resolved geographies plus the rejected inputs, so the caller can report
    exactly which candidates were dropped instead of silently shrinking the comparison.
    """
    resolved: list[Geography] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for entry in raw_geographies:
        try:
            geography = resolve_geography(entry)
        except UnsupportedGeographyError:
            rejected.append(entry)
            continue
        if geography.slug not in seen:
            seen.add(geography.slug)
            resolved.append(geography)

    return resolved, rejected


def select_metrics(
    registry: MetricRegistry,
    geographies: list[Geography],
    requested_metric_ids: list[str] | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Choose approved metrics for the candidate set.

    Returns the selected metric ids and a list of ``(metric_id, reason)`` pairs for
    metrics that were dropped before any API call, so the trace can show the decision.
    """
    geography_types = [geography.geography_type for geography in geographies]
    dropped: list[tuple[str, str]] = []

    if requested_metric_ids:
        candidates = []
        for metric_id in requested_metric_ids:
            metric = registry.get(metric_id)
            if metric is None:
                dropped.append(
                    (
                        metric_id,
                        "Not present in the approved metric registry. Only datapoints "
                        "verified against the live Atlas API can be requested.",
                    )
                )
                continue
            candidates.append(metric)
    else:
        candidates = registry.all()

    selected: list[str] = []
    for metric in candidates:
        unsupported_levels = [t for t in geography_types if not metric.supports(t)]
        if unsupported_levels:
            dropped.append(
                (
                    metric.metric_id,
                    f"{metric.source} does not publish this datapoint at the "
                    + ", ".join(sorted({str(level) for level in unsupported_levels}))
                    + " level, so it cannot describe the candidate regions.",
                )
            )
            continue
        selected.append(metric.metric_id)

    return selected, dropped


def default_category_weights() -> dict[MetricCategory, float]:
    from scoring.service import DEFAULT_CATEGORY_WEIGHTS

    return dict(DEFAULT_CATEGORY_WEIGHTS)
