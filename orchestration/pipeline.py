"""End-to-end orchestration.

Fixed sequence, with the trace recorded at every step so a reviewer can reconstruct
exactly what was asked, what was called, what was rejected, and how the numbers were
produced:

    interpret -> resolve geographies -> select metrics -> fetch -> validate
              -> score -> assess sufficiency -> explain

The orchestrator decides *what to ask for*. It never decides *what is true*: values come
from the fetcher, comparability from the validator, and arithmetic from the scorer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from api.client import AtlasClient, AtlasError
from api.geographies import DEMO_TOKEN_SCOPE_NOTE
from core.config import MissingTokenError, Settings, get_settings
from core.logging import get_logger, log_event
from explanation.narrator import build_recommendation
from metrics.registry import MetricRegistry, get_registry
from models.analysis import (
    AnalysisPlan,
    AnalysisResult,
    Limitation,
    LimitationSeverity,
    Refusal,
    TraceEntry,
)
from models.evidence import EvidencePackage, ExcludedMetric, ValidationStatus
from models.geography import Geography
from models.metrics import MetricCategory
from orchestration.intent import (
    SUPPORTED_CAPABILITIES,
    RefusalKind,
    interpret_question,
    resolve_candidate_geographies,
    select_metrics,
)
from orchestration.fetcher import fetch_evidence, new_package_id
from scoring.service import ScoringConfig, ScoringService
from validation.compatibility import CompatibilityPolicy, validate_evidence

logger = get_logger("orchestration.pipeline")


@dataclass
class AnalysisRequest:
    question: str
    geographies: list[str]
    category_weights: dict[MetricCategory, float] | None = None
    metric_ids: list[str] | None = None
    retailer_profile: str = "National mainstream apparel retailer (GAP-like)"
    use_llm_narrative: bool = True


class AnalysisPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        registry: MetricRegistry | None = None,
        policy: CompatibilityPolicy | None = None,
        client_factory=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or get_registry()
        self.policy = policy or CompatibilityPolicy()
        # Injectable so tests can supply a mock transport without monkeypatching.
        self._client_factory = client_factory or (lambda: AtlasClient(self.settings))

    def run(self, request: AnalysisRequest) -> AnalysisResult:
        trace: list[TraceEntry] = []
        limitations: list[Limitation] = []

        # ---------------------------------------------------------------- 1. Intent
        intent = interpret_question(request.question)
        trace.append(
            TraceEntry(
                step="parse_intent",
                detail=(
                    "Question sanitized and classified before any tool selection."
                    if intent.plan_ok
                    else f"Question refused: {intent.refusal_kind}."
                ),
                payload={
                    "sanitized_question": intent.sanitized_question,
                    "answerable": intent.plan_ok,
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
                "request_refused",
                kind=str(intent.refusal_kind),
                injection=intent.flagged_injection,
            )
            return AnalysisResult(
                plan=None,
                evidence=None,
                recommendation=None,
                refusal=intent.refusal,
                limitations=self._base_limitations(),
                trace=trace,
            )

        # ------------------------------------------------------- 2. Resolve geographies
        geographies, rejected = resolve_candidate_geographies(request.geographies)
        trace.append(
            TraceEntry(
                step="resolve_geographies",
                detail=(
                    f"Resolved {len(geographies)} candidate region(s) against the token's "
                    f"allowlist; rejected {len(rejected)}."
                ),
                payload={
                    "resolved": [g.slug for g in geographies],
                    "rejected": rejected,
                },
            )
        )
        if rejected:
            limitations.append(
                Limitation(
                    title="Requested regions outside the licensed footprint",
                    detail=(
                        "These candidates were dropped because the active token does not "
                        f"license them: {', '.join(rejected)}. {DEMO_TOKEN_SCOPE_NOTE}"
                    ),
                    severity=LimitationSeverity.CAUTION,
                )
            )

        if len(geographies) < 2:
            return self._refuse_insufficient_geographies(
                intent.sanitized_question, geographies, rejected, trace, limitations
            )

        # ----------------------------------------------------------- 3. Select metrics
        metric_ids, dropped = select_metrics(self.registry, geographies, request.metric_ids)
        trace.append(
            TraceEntry(
                step="select_metrics",
                detail=(
                    f"Selected {len(metric_ids)} approved metric(s); excluded {len(dropped)} "
                    "before any API call."
                ),
                payload={
                    "selected": metric_ids,
                    "excluded": [
                        {"metric_id": metric_id, "reason": reason}
                        for metric_id, reason in dropped
                    ],
                },
            )
        )

        pre_excluded = [
            ExcludedMetric(
                metric_id=metric_id,
                display_name=(
                    metric.display_name
                    if (metric := self.registry.get(metric_id)) is not None
                    else metric_id
                ),
                atlas_datapoint=(
                    self.registry.get(metric_id).atlas_datapoint
                    if self.registry.get(metric_id) is not None
                    else "n/a"
                ),
                reason=reason,
                status=ValidationStatus.MISSING,
                affected_geographies=[g.slug for g in geographies],
            )
            for metric_id, reason in dropped
        ]

        plan = AnalysisPlan(
            question=intent.sanitized_question,
            geographies=geographies,
            metric_ids=metric_ids,
            category_weights=request.category_weights or ScoringConfig().category_weights,
            rationale=(
                f"Compare {len(geographies)} candidate region(s) for a "
                f"{request.retailer_profile} using {len(metric_ids)} verified Atlas metric(s) "
                "across market potential, customer fit, economic attractiveness, "
                "accessibility, and growth outlook."
            ),
            answerable=True,
        )

        if not metric_ids:
            return self._refuse_no_metrics(plan, pre_excluded, trace, limitations)

        # -------------------------------------------------------------- 4. Fetch data
        metrics = [self.registry.require(metric_id) for metric_id in metric_ids]
        try:
            client = self._client_factory()
        except MissingTokenError as exc:
            return self._refuse_missing_token(plan, str(exc), trace, limitations)

        try:
            with client:
                fetched = fetch_evidence(client, metrics, geographies)
        except AtlasError as exc:
            return self._refuse_api_failure(plan, str(exc), trace, limitations)

        trace.append(
            TraceEntry(
                step="atlas_calls",
                detail=f"Issued {len(fetched.calls)} Atlas request(s).",
                payload={
                    "calls": [
                        {
                            "call_id": call.call_id,
                            "url": call.url,
                            "status_code": call.status_code,
                            "attempts": call.attempts,
                            "elapsed_seconds": call.elapsed_seconds,
                            "error": call.error,
                        }
                        for call in fetched.calls
                    ],
                    "errors": fetched.errors,
                },
            )
        )

        if fetched.errors and not any(item.is_usable for item in fetched.items):
            return self._refuse_api_failure(plan, "; ".join(fetched.errors), trace, limitations)

        # ----------------------------------------------------------------- 5. Validate
        outcome = validate_evidence(fetched.items, geographies, self.policy)
        excluded = pre_excluded + fetched.excluded + outcome.excluded
        trace.append(
            TraceEntry(
                step="validate_evidence",
                detail=(
                    f"{len(outcome.usable_metric_ids)} metric(s) passed every comparability "
                    f"gate; {len(outcome.excluded)} were rejected during validation."
                ),
                payload={
                    "passed": outcome.usable_metric_ids,
                    "rejected": [
                        {
                            "metric_id": entry.metric_id,
                            "status": str(entry.status),
                            "reason": entry.reason,
                        }
                        for entry in outcome.excluded
                    ],
                    "warnings": outcome.warnings,
                },
            )
        )

        package = EvidencePackage(
            package_id=new_package_id(),
            geographies=geographies,
            items=outcome.items,
            excluded_metrics=excluded,
            raw_calls=fetched.calls,
        )

        # ------------------------------------------------------------------- 6. Score
        # The full planned set is handed to scoring, not just the survivors, so that a
        # metric dropped by validation still appears as an explicit zero-weight row and
        # produces a disclosed weight renormalization.
        scoring_metrics = {metric_id: self.registry.require(metric_id) for metric_id in metric_ids}
        config = ScoringConfig(
            category_weights=request.category_weights or ScoringConfig().category_weights
        )
        scoring = ScoringService(config).score(package, scoring_metrics)

        # Attach normalized values back onto the evidence so the panel can show both.
        enriched = []
        for item in package.items:
            normalization = scoring.normalizations.get(item.metric.metric_id)
            if normalization and item.geography.slug in normalization.scores:
                enriched.append(
                    item.model_copy(
                        update={"normalized_value": normalization.scores[item.geography.slug]}
                    )
                )
            else:
                enriched.append(item)
        package = package.model_copy(update={"items": enriched})

        trace.append(
            TraceEntry(
                step="deterministic_scoring",
                detail=(
                    f"Normalized and weighted {len(scoring.normalizations)} metric(s). "
                    f"Reproducibility hash {scoring.reproducibility_hash}."
                ),
                payload={
                    "reproducibility_hash": scoring.reproducibility_hash,
                    "category_weights": {
                        str(category): round(weight, 4)
                        for category, weight in config.normalized().items()
                    },
                    "normalizations": {
                        metric_id: {
                            "method": str(result.method),
                            "direction": str(result.direction),
                            "observed_min": result.observed_min,
                            "observed_max": result.observed_max,
                            "detail": result.detail,
                            "scores": result.scores,
                        }
                        for metric_id, result in sorted(scoring.normalizations.items())
                    },
                    "weight_adjustments": [
                        {
                            "metric_id": adjustment.metric_id,
                            "category": str(adjustment.category),
                            "original_weight": adjustment.original_weight,
                            "reason": adjustment.reason,
                        }
                        for adjustment in scoring.weight_adjustments
                    ],
                    "ranking": [
                        {
                            "rank": region.rank,
                            "geography": region.geography.slug,
                            "overall_score": region.overall_score,
                        }
                        for region in scoring.ranked_regions
                    ],
                },
            )
        )

        limitations.extend(
            self._build_limitations(outcome.warnings, excluded, package, scoring.insufficient_reason)
        )

        # ------------------------------------------------- 7. Insufficient evidence gate
        if scoring.insufficient_evidence:
            refusal = Refusal(
                question=plan.question,
                reason=(
                    "The available evidence does not support ranking these regions "
                    f"reliably. {scoring.insufficient_reason}"
                ),
                unsupported_because=[
                    scoring.insufficient_reason or "Insufficient comparable evidence.",
                    f"{len(excluded)} metric(s) were excluded by validation, so the score "
                    "rests on a narrower base than the model intends.",
                ],
                required_inputs=[
                    "Additional Atlas metrics that are published at every candidate region's "
                    "geographic level.",
                    "A commercial StateBook license covering a wider set of candidate regions.",
                    "Retailer-supplied inputs such as site costs, foot traffic, and competitor "
                    "presence to break a statistical tie on business grounds.",
                ],
                offered_alternative=(
                    "The per-metric comparison and full evidence table are still shown below, "
                    "with every value traceable to its Atlas response. They can be reviewed "
                    "directly, but they should not be collapsed into a single ranking."
                ),
                supported_capabilities=SUPPORTED_CAPABILITIES,
            )
            trace.append(
                TraceEntry(
                    step="sufficiency_gate",
                    detail="Ranking withheld: evidence is insufficient to separate the candidates.",
                    payload={"reason": scoring.insufficient_reason},
                )
            )
            return AnalysisResult(
                plan=plan,
                evidence=package,
                recommendation=None,
                refusal=refusal,
                limitations=limitations,
                weight_adjustments=scoring.weight_adjustments,
                trace=trace,
                reproducibility_hash=scoring.reproducibility_hash,
            )

        # ----------------------------------------------------------------- 8. Explain
        recommendation = build_recommendation(
            plan=plan,
            package=package,
            scoring=scoring,
            settings=self.settings,
            use_llm=request.use_llm_narrative,
            retailer_profile=request.retailer_profile,
            limitations=limitations,
        )
        trace.append(
            TraceEntry(
                step="explanation",
                detail=(
                    f"Narrative produced by {recommendation.generated_by} from the validated "
                    f"evidence package only, citing {len(recommendation.citations)} evidence "
                    "object(s)."
                ),
                payload={
                    "generated_by": recommendation.generated_by,
                    "citations": recommendation.citations,
                    "evidence_package_id": package.package_id,
                },
            )
        )

        log_event(
            logger,
            logging.INFO,
            "analysis_complete",
            geographies=len(geographies),
            metrics_scored=len(scoring.normalizations),
            completeness=round(package.completeness, 3),
            hash=scoring.reproducibility_hash,
        )

        return AnalysisResult(
            plan=plan,
            evidence=package,
            recommendation=recommendation,
            refusal=None,
            limitations=limitations,
            weight_adjustments=scoring.weight_adjustments,
            trace=trace,
            reproducibility_hash=scoring.reproducibility_hash,
        )

    # ------------------------------------------------------------------ refusal helpers

    def _base_limitations(self) -> list[Limitation]:
        limitations = [
            Limitation(
                title="Demo token geographic restriction",
                detail=DEMO_TOKEN_SCOPE_NOTE,
                severity=LimitationSeverity.INFO if not self.settings.is_demo_token else LimitationSeverity.CAUTION,
            ),
            Limitation(
                title="Market indicators are not a site-selection decision",
                detail=(
                    "Atlas describes geographic areas. A real store investment additionally "
                    "requires site-level rent and build-out cost, observed foot traffic, "
                    "competitor locations and formats, cannibalization of the existing store "
                    "network, category margin, supply-chain cost to serve, and the retailer's "
                    "own transaction data. None of that is available here."
                ),
                severity=LimitationSeverity.CAUTION,
            ),
        ]
        return limitations

    def _build_limitations(
        self,
        warnings: list[str],
        excluded: list[ExcludedMetric],
        package: EvidencePackage,
        insufficient_reason: str | None,
    ) -> list[Limitation]:
        limitations = self._base_limitations()

        if excluded:
            limitations.append(
                Limitation(
                    title=f"{len(excluded)} metric(s) excluded from the score",
                    detail="; ".join(
                        f"{entry.display_name}: {entry.reason}" for entry in excluded
                    ),
                    severity=LimitationSeverity.CAUTION,
                )
            )

        for warning in warnings:
            limitations.append(
                Limitation(
                    title="Data comparability note",
                    detail=warning,
                    severity=LimitationSeverity.CAUTION,
                )
            )

        if package.completeness < 1.0:
            limitations.append(
                Limitation(
                    title="Incomplete evidence coverage",
                    detail=(
                        f"{package.completeness:.0%} of attempted region/metric combinations "
                        "returned a usable value. Regions with gaps are scored on their "
                        "remaining metrics with weights renormalized, which makes their "
                        "scores less directly comparable to fully covered regions."
                    ),
                    severity=LimitationSeverity.CAUTION,
                )
            )

        if len(package.geographies) == 2:
            limitations.append(
                Limitation(
                    title="Two-region comparison produces extreme normalized scores",
                    detail=(
                        "Min-max normalization places the better region at 100 and the other "
                        "at 0 on every metric, regardless of whether the gap between them is "
                        "large or trivial. The ordering is meaningful; the size of the gap is "
                        "not. Add a third region, or read the raw values in the evidence "
                        "panel, to judge magnitude."
                    ),
                    severity=LimitationSeverity.CAUTION,
                )
            )

        limitations.append(
            Limitation(
                title="Survey estimates carry sampling error",
                detail=(
                    "American Community Survey values are 5-year rolling estimates with "
                    "margins of error that widen for smaller places. Small differences "
                    "between similarly sized regions may not be statistically meaningful."
                ),
                severity=LimitationSeverity.INFO,
            )
        )

        if insufficient_reason:
            limitations.append(
                Limitation(
                    title="Ranking withheld",
                    detail=insufficient_reason,
                    severity=LimitationSeverity.BLOCKING,
                )
            )

        return limitations

    def _refuse_insufficient_geographies(
        self,
        question: str,
        geographies: list[Geography],
        rejected: list[str],
        trace: list[TraceEntry],
        limitations: list[Limitation],
    ) -> AnalysisResult:
        refusal = Refusal(
            question=question,
            reason=(
                f"A comparison needs at least two candidate regions; {len(geographies)} "
                "resolved successfully."
            ),
            unsupported_because=(
                [f"These inputs are not licensed by the active token: {', '.join(rejected)}."]
                if rejected
                else ["Fewer than two candidate regions were supplied."]
            )
            + [DEMO_TOKEN_SCOPE_NOTE],
            required_inputs=["Two or more candidate regions from the licensed footprint."],
            offered_alternative=(
                "Pick two or more regions from the supported list and the comparison will run."
            ),
            supported_capabilities=SUPPORTED_CAPABILITIES,
        )
        trace.append(
            TraceEntry(
                step="sufficiency_gate",
                detail="Refused: fewer than two candidate regions resolved.",
                payload={"resolved": [g.slug for g in geographies], "rejected": rejected},
            )
        )
        return AnalysisResult(
            plan=None,
            evidence=None,
            recommendation=None,
            refusal=refusal,
            limitations=limitations or self._base_limitations(),
            trace=trace,
        )

    def _refuse_no_metrics(
        self,
        plan: AnalysisPlan,
        excluded: list[ExcludedMetric],
        trace: list[TraceEntry],
        limitations: list[Limitation],
    ) -> AnalysisResult:
        refusal = Refusal(
            question=plan.question,
            reason=(
                "No approved metric is published at the geographic level of every candidate "
                "region, so there is nothing comparable to score."
            ),
            unsupported_because=[entry.reason for entry in excluded]
            or ["No metric in the registry supports this combination of geographic levels."],
            required_inputs=[
                "Candidate regions at a consistent geographic level.",
                "Metrics published at that level by the underlying source.",
            ],
            offered_alternative=(
                "Compare regions of the same type - all cities, or all counties - so the "
                "available datapoints describe the same kind of area."
            ),
            supported_capabilities=SUPPORTED_CAPABILITIES,
        )
        trace.append(
            TraceEntry(
                step="sufficiency_gate",
                detail="Refused: no approved metric covers all candidate geographic levels.",
                payload={"excluded": [entry.metric_id for entry in excluded]},
            )
        )
        return AnalysisResult(
            plan=plan,
            evidence=None,
            recommendation=None,
            refusal=refusal,
            limitations=limitations or self._base_limitations(),
            trace=trace,
        )

    def _refuse_missing_token(
        self,
        plan: AnalysisPlan,
        message: str,
        trace: list[TraceEntry],
        limitations: list[Limitation],
    ) -> AnalysisResult:
        refusal = Refusal(
            question=plan.question,
            reason=(
                "No StateBook Atlas token is configured, so no data can be retrieved. The "
                "system will not answer from memory or from cached assumptions."
            ),
            unsupported_because=[message],
            required_inputs=[
                "Set STATEBOOK_API_TOKEN in the environment. Copy .env.example to .env and "
                "set STATEBOOK_API_TOKEN=demo to use the public evaluation token."
            ],
            offered_alternative=(
                "Configure the token and re-run the comparison; nothing else needs to change."
            ),
            supported_capabilities=SUPPORTED_CAPABILITIES,
        )
        trace.append(
            TraceEntry(step="atlas_calls", detail="Refused: no API token configured.")
        )
        return AnalysisResult(
            plan=plan,
            evidence=None,
            recommendation=None,
            refusal=refusal,
            limitations=limitations or self._base_limitations(),
            trace=trace,
        )

    def _refuse_api_failure(
        self,
        plan: AnalysisPlan,
        message: str,
        trace: list[TraceEntry],
        limitations: list[Limitation],
    ) -> AnalysisResult:
        refusal = Refusal(
            question=plan.question,
            reason=(
                "The StateBook Atlas API could not be reached or returned an error, so no "
                "evidence is available. No ranking is produced, because any answer would be "
                "unsupported by data."
            ),
            unsupported_because=[
                f"Atlas request failed: {message}",
                "The system has no fallback data source and does not estimate values.",
            ],
            required_inputs=[
                "A reachable Atlas endpoint and a valid token.",
                "Confirmation that the requested geographies are licensed.",
            ],
            offered_alternative=(
                "Retry once the API is reachable. The trace panel shows the exact requests "
                "that were attempted and how many times each was retried."
            ),
            supported_capabilities=SUPPORTED_CAPABILITIES,
        )
        trace.append(
            TraceEntry(
                step="atlas_calls",
                detail="Refused: Atlas API failure.",
                payload={"error": message},
            )
        )
        return AnalysisResult(
            plan=plan,
            evidence=None,
            recommendation=None,
            refusal=refusal,
            limitations=limitations or self._base_limitations(),
            trace=trace,
        )


def run_analysis(request: AnalysisRequest, **kwargs) -> AnalysisResult:
    return AnalysisPipeline(**kwargs).run(request)
