"""Comparability gates.

Two numbers being present is not the same as two numbers being comparable. This layer
decides, per metric, whether the values Atlas returned for the candidate regions may be
placed on the same axis at all. Anything that fails is marked and excluded with a reason
rather than quietly averaged in.

Rules applied per metric, across the candidate set:

1. Schema      - the value must be numeric and carry the metadata the model relies on.
2. Geography   - Atlas must have answered at the same geographic resolution for every
                 region. A silent context shift (city -> metro for one region only) makes
                 the comparison meaningless.
3. Period      - the reporting periods must agree within the configured tolerance.
4. Source      - the values must come from the same Atlas source.
5. Unit        - the registry unit must not contradict the datapoint's observed form.
6. Coverage    - at least two regions must survive, or there is nothing to rank.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from models.evidence import EvidenceItem, ExcludedMetric, ValidationStatus
from models.geography import Geography


@dataclass(frozen=True)
class CompatibilityPolicy:
    """Tunable strictness. Defaults are the conservative choice."""

    max_period_spread_years: int = 0
    """Allowed difference between the newest and oldest period for one metric."""

    require_uniform_source: bool = True
    require_uniform_geography_resolution: bool = True
    min_regions_per_metric: int = 2
    """A metric observed in only one region cannot discriminate between candidates."""


@dataclass
class ValidationOutcome:
    items: list[EvidenceItem] = field(default_factory=list)
    excluded: list[ExcludedMetric] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def usable_metric_ids(self) -> list[str]:
        return sorted({item.metric.metric_id for item in self.items if item.is_usable})


def _period_year(period: str | None) -> int | None:
    if not period:
        return None
    digits = "".join(character for character in period if character.isdigit())
    if len(digits) >= 4:
        try:
            return int(digits[:4])
        except ValueError:
            return None
    return None


def _mark(item: EvidenceItem, status: ValidationStatus, note: str) -> EvidenceItem:
    return item.model_copy(
        update={
            "validation_status": status,
            "validation_notes": [*item.validation_notes, note],
        }
    )


def _exclude(
    items: list[EvidenceItem], reason: str, status: ValidationStatus
) -> ExcludedMetric:
    reference = items[0]
    return ExcludedMetric(
        metric_id=reference.metric.metric_id,
        display_name=reference.metric.display_name,
        atlas_datapoint=reference.atlas_datapoint,
        reason=reason,
        status=status,
        affected_geographies=sorted({item.geography.slug for item in items}),
    )


def validate_evidence(
    items: list[EvidenceItem],
    geographies: list[Geography],
    policy: CompatibilityPolicy | None = None,
) -> ValidationOutcome:
    """Apply every comparability gate and return the surviving evidence plus exclusions."""
    policy = policy or CompatibilityPolicy()
    outcome = ValidationOutcome()

    requested_types = {geography.geography_type for geography in geographies}
    if len(requested_types) > 1:
        outcome.warnings.append(
            "Candidate regions mix geographic levels ("
            + ", ".join(sorted(str(t) for t in requested_types))
            + "). Counts such as total population are not directly comparable across "
            "different geographic levels; interpret magnitude-based metrics with care."
        )

    by_metric: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in items:
        by_metric[item.metric.metric_id].append(item)

    for metric_id, metric_items in sorted(by_metric.items()):
        checked: list[EvidenceItem] = []

        # 1. Schema and presence.
        for item in metric_items:
            if item.raw_value is None:
                checked.append(
                    _mark(item, ValidationStatus.MISSING, "Atlas returned no value for this region.")
                )
            elif not isinstance(item.raw_value, (int, float)):
                checked.append(
                    _mark(
                        item,
                        ValidationStatus.SCHEMA_INVALID,
                        f"Expected a numeric value, got {type(item.raw_value).__name__}.",
                    )
                )
            elif item.period is None:
                checked.append(
                    _mark(
                        item,
                        ValidationStatus.SCHEMA_INVALID,
                        "Atlas returned a value without a reporting period, so it cannot be "
                        "shown to be contemporaneous with the other regions.",
                    )
                )
            else:
                checked.append(item)

        present = [item for item in checked if item.validation_status == ValidationStatus.VALID]

        if not present:
            outcome.items.extend(checked)
            outcome.excluded.append(
                _exclude(
                    metric_items,
                    "Atlas returned no usable value for any candidate region.",
                    ValidationStatus.MISSING,
                )
            )
            continue

        # 2. Geographic resolution.
        if policy.require_uniform_geography_resolution:
            # An inconsistent context shift is the real hazard: Atlas answered some regions
            # at the level that was asked for and silently widened others. Those values
            # describe different kinds of area and must not share an axis. A comparison the
            # user deliberately made across levels is handled separately below.
            shifted_slugs = sorted(
                item.geography.slug for item in present if item.geography_context_shifted
            )
            if shifted_slugs and len(shifted_slugs) != len(present):
                note = (
                    "Atlas widened the geographic context for some regions but not others ("
                    + ", ".join(shifted_slugs)
                    + " were answered at a broader level), so the values do not describe "
                    "comparable areas."
                )
                checked = [
                    _mark(item, ValidationStatus.INCOMPARABLE_GEOGRAPHY, note)
                    if item.validation_status == ValidationStatus.VALID
                    else item
                    for item in checked
                ]
                outcome.items.extend(checked)
                outcome.excluded.append(
                    _exclude(metric_items, note, ValidationStatus.INCOMPARABLE_GEOGRAPHY)
                )
                continue

            # A magnitude compared across different geographic levels is meaningless: a
            # county contains its cities, so the count is guaranteed to be larger for
            # reasons that have nothing to do with market attractiveness. Rates and shares
            # remain comparable and are allowed through with a disclosure.
            levels = {
                (item.reported_geography or item.geography.slug).split(":", 1)[0]
                for item in present
            }
            if len(levels) > 1 and present[0].metric.is_count:
                note = (
                    "This metric is a count, and the candidate regions span different "
                    "geographic levels (" + ", ".join(sorted(levels)) + "). A larger area "
                    "necessarily reports a larger count, so ranking on it would measure "
                    "geographic scope rather than market attractiveness."
                )
                checked = [
                    _mark(item, ValidationStatus.INCOMPARABLE_GEOGRAPHY, note)
                    if item.validation_status == ValidationStatus.VALID
                    else item
                    for item in checked
                ]
                outcome.items.extend(checked)
                outcome.excluded.append(
                    _exclude(metric_items, note, ValidationStatus.INCOMPARABLE_GEOGRAPHY)
                )
                continue

            if len(levels) > 1:
                outcome.warnings.append(
                    f"{present[0].metric.display_name}: compared across different geographic "
                    "levels (" + ", ".join(sorted(levels)) + "). This is valid for a rate, "
                    "but the regions are not peers and one may contain the other."
                )

            # A metric whose values all resolve to one shared parent geography carries no
            # information about the candidates: every region would receive the identical
            # number. Ranking on it would manufacture a distinction that does not exist.
            reported = {item.reported_geography or item.geography.slug for item in present}
            requested = {item.geography.slug for item in present}
            if len(reported) == 1 and len(requested) > 1 and reported != requested:
                shared = next(iter(reported))
                note = (
                    f"Atlas answered every candidate region with the same value for "
                    f"{shared}, because this datapoint is not published at the requested "
                    "geographic level. It cannot distinguish between the candidates."
                )
                checked = [
                    _mark(item, ValidationStatus.INCOMPARABLE_GEOGRAPHY, note)
                    if item.validation_status == ValidationStatus.VALID
                    else item
                    for item in checked
                ]
                outcome.items.extend(checked)
                outcome.excluded.append(
                    _exclude(metric_items, note, ValidationStatus.INCOMPARABLE_GEOGRAPHY)
                )
                continue

            shifted = [item for item in present if item.geography_context_shifted]
            if shifted:
                outcome.warnings.append(
                    f"{metric_items[0].metric.display_name}: "
                    "Atlas resolved this metric at a broader geography than requested for "
                    + ", ".join(sorted(item.geography.slug for item in shifted))
                    + ". The comparison remains internally consistent but does not isolate "
                    "the requested region."
                )

        # 3. Period agreement.
        years = [year for year in (_period_year(item.period) for item in present) if year is not None]
        if years:
            spread = max(years) - min(years)
            if spread > policy.max_period_spread_years:
                periods = sorted({item.period or "unknown" for item in present})
                note = (
                    f"Reporting periods differ by {spread} year(s) across regions "
                    f"({', '.join(periods)}), which exceeds the allowed spread of "
                    f"{policy.max_period_spread_years}."
                )
                checked = [
                    _mark(item, ValidationStatus.INCOMPARABLE_PERIOD, note)
                    if item.validation_status == ValidationStatus.VALID
                    else item
                    for item in checked
                ]
                outcome.items.extend(checked)
                outcome.excluded.append(
                    _exclude(metric_items, note, ValidationStatus.INCOMPARABLE_PERIOD)
                )
                continue

        # 4. Source agreement.
        if policy.require_uniform_source:
            sources = {item.source for item in present if item.source}
            if len(sources) > 1:
                note = (
                    "Values come from different Atlas sources ("
                    + ", ".join(sorted(str(source) for source in sources))
                    + "), which use different methodologies."
                )
                checked = [
                    _mark(item, ValidationStatus.INCOMPARABLE_SOURCE, note)
                    if item.validation_status == ValidationStatus.VALID
                    else item
                    for item in checked
                ]
                outcome.items.extend(checked)
                outcome.excluded.append(
                    _exclude(metric_items, note, ValidationStatus.INCOMPARABLE_SOURCE)
                )
                continue

        # 5. Unit sanity: a metric declared as a percentage must behave like one.
        metric = present[0].metric
        if metric.is_rate and any(
            item.raw_value is not None and not (-1000.0 <= float(item.raw_value) <= 1000.0)
            for item in present
        ):
            note = (
                f"Values are declared as {metric.unit} but fall outside a plausible "
                "percentage range, suggesting a unit mismatch."
            )
            checked = [
                _mark(item, ValidationStatus.INCOMPARABLE_UNIT, note)
                if item.validation_status == ValidationStatus.VALID
                else item
                for item in checked
            ]
            outcome.items.extend(checked)
            outcome.excluded.append(
                _exclude(metric_items, note, ValidationStatus.INCOMPARABLE_UNIT)
            )
            continue

        # 6. Coverage.
        still_valid = [item for item in checked if item.validation_status == ValidationStatus.VALID]
        if len(still_valid) < policy.min_regions_per_metric:
            outcome.items.extend(checked)
            outcome.excluded.append(
                _exclude(
                    metric_items,
                    f"Only {len(still_valid)} of {len(metric_items)} candidate regions have a "
                    f"usable value; at least {policy.min_regions_per_metric} are required to "
                    "rank on this metric.",
                    ValidationStatus.MISSING,
                )
            )
            continue

        if len(still_valid) < len(metric_items):
            missing = sorted(
                item.geography.display_name
                for item in checked
                if item.validation_status != ValidationStatus.VALID
            )
            outcome.warnings.append(
                f"{metric.display_name}: no value for {', '.join(missing)}. Those regions are "
                "scored on their remaining metrics with weights renormalized."
            )

        outcome.items.extend(checked)

    return outcome
