"""Fetch evidence from Atlas for an approved set of metrics and geographies.

The fetcher is the only component that turns an API response into an
:class:`EvidenceItem`. It never invents an item: if Atlas did not answer, the item is
recorded as missing with the call id that failed, so the gap is visible rather than absent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from api.client import AtlasClient, AtlasError
from api.parsing import MalformedAtlasResponse, ParsedResponse, parse_getdata
from core.logging import get_logger, log_event
from models.evidence import EvidenceItem, ExcludedMetric, RawCall, ValidationStatus
from models.geography import Geography
from models.metrics import MetricDefinition

logger = get_logger("orchestration.fetcher")


@dataclass
class FetchResult:
    items: list[EvidenceItem] = field(default_factory=list)
    excluded: list[ExcludedMetric] = field(default_factory=list)
    calls: list[RawCall] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _evidence_id(metric_id: str, slug: str) -> str:
    return f"ev_{metric_id}_{slug.replace(':', '_').replace('-', '_')}"


def _missing_item(
    metric: MetricDefinition,
    geography: Geography,
    note: str,
    call_id: str | None,
    status: ValidationStatus = ValidationStatus.MISSING,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=_evidence_id(metric.metric_id, geography.slug),
        metric=metric,
        geography=geography,
        atlas_datapoint=metric.atlas_datapoint,
        raw_value=None,
        period=None,
        source=None,
        validation_status=status,
        validation_notes=[note],
        call_id=call_id,
    )


def _items_from_parsed(
    parsed: ParsedResponse,
    metrics: list[MetricDefinition],
    geographies: list[Geography],
    call: RawCall,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for metric in metrics:
        for geography in geographies:
            observation = parsed.latest(
                geography.slug, metric.atlas_datapoint, item=metric.atlas_item_code
            )
            if observation is None or observation.value is None:
                items.append(
                    _missing_item(
                        metric,
                        geography,
                        "Atlas returned no value for this datapoint in this geography.",
                        call.call_id,
                    )
                )
                continue

            if not isinstance(observation.value, (int, float)):
                items.append(
                    _missing_item(
                        metric,
                        geography,
                        f"Atlas returned a non-numeric value ({observation.value!r}).",
                        call.call_id,
                        status=ValidationStatus.SCHEMA_INVALID,
                    )
                )
                continue

            metadata = parsed.datapoint_metadata.get(metric.atlas_datapoint, {})
            source = observation.source or metadata.get("attribution") or metric.source

            items.append(
                EvidenceItem(
                    evidence_id=_evidence_id(metric.metric_id, geography.slug),
                    metric=metric,
                    geography=geography,
                    atlas_datapoint=metric.atlas_datapoint,
                    raw_value=float(observation.value),
                    period=observation.period,
                    source=source,
                    reported_geography=observation.reported_geography,
                    call_id=call.call_id,
                )
            )
    return items


def fetch_evidence(
    client: AtlasClient,
    metrics: list[MetricDefinition],
    geographies: list[Geography],
) -> FetchResult:
    """Retrieve every metric for every geography, recording calls and failures."""
    result = FetchResult()
    if not metrics or not geographies:
        return result

    slugs = [geography.slug for geography in geographies]
    scalar_metrics = [metric for metric in metrics if not metric.is_collection_metric]
    collection_metrics = [metric for metric in metrics if metric.is_collection_metric]

    if scalar_metrics:
        datapoints = sorted({metric.atlas_datapoint for metric in scalar_metrics})
        try:
            body, call = client.get_data(datapoints, slugs, include_metadata=True)
            result.calls.append(call)
            parsed = parse_getdata(body)
            result.items.extend(_items_from_parsed(parsed, scalar_metrics, geographies, call))
        except MalformedAtlasResponse as exc:
            call = client.calls[-1] if client.calls else None
            result.calls.extend(c for c in ([call] if call else []) if c not in result.calls)
            message = f"Atlas returned a response that does not match the documented schema: {exc}"
            result.errors.append(message)
            for metric in scalar_metrics:
                result.excluded.append(
                    ExcludedMetric(
                        metric_id=metric.metric_id,
                        display_name=metric.display_name,
                        atlas_datapoint=metric.atlas_datapoint,
                        reason=message,
                        status=ValidationStatus.SCHEMA_INVALID,
                        affected_geographies=slugs,
                    )
                )
                for geography in geographies:
                    result.items.append(
                        _missing_item(
                            metric,
                            geography,
                            message,
                            call.call_id if call else None,
                            status=ValidationStatus.SCHEMA_INVALID,
                        )
                    )
        except AtlasError as exc:
            if exc.call and exc.call not in result.calls:
                result.calls.append(exc.call)
            message = str(exc)
            result.errors.append(message)
            log_event(logger, logging.ERROR, "atlas_fetch_failed", error=message)
            for metric in scalar_metrics:
                for geography in geographies:
                    result.items.append(
                        _missing_item(
                            metric,
                            geography,
                            f"Atlas request failed: {message}",
                            exc.call.call_id if exc.call else None,
                        )
                    )

    # Collection metrics are grouped by collection so one request serves all of them.
    by_collection: dict[str, list[MetricDefinition]] = {}
    for metric in collection_metrics:
        by_collection.setdefault(metric.atlas_collection or "", []).append(metric)

    for collection, group in by_collection.items():
        datapoints = sorted({metric.atlas_datapoint for metric in group})
        item_datapoint = next(
            (metric.atlas_item_datapoint for metric in group if metric.atlas_item_datapoint), None
        )
        item_codes = sorted({metric.atlas_item_code for metric in group if metric.atlas_item_code})
        try:
            body, call = client.get_collection(
                collection,
                datapoints,
                slugs,
                item_datapoint=item_datapoint,
                item_codes=item_codes,
                include_metadata=True,
            )
            result.calls.append(call)
            parsed = parse_getdata(body)
            result.items.extend(_items_from_parsed(parsed, group, geographies, call))
        except (AtlasError, MalformedAtlasResponse) as exc:
            call_obj = getattr(exc, "call", None)
            if call_obj and call_obj not in result.calls:
                result.calls.append(call_obj)
            message = f"Atlas collection request for {collection} failed: {exc}"
            result.errors.append(message)
            log_event(logger, logging.ERROR, "atlas_collection_failed", collection=collection, error=str(exc))
            for metric in group:
                result.excluded.append(
                    ExcludedMetric(
                        metric_id=metric.metric_id,
                        display_name=metric.display_name,
                        atlas_datapoint=metric.atlas_datapoint,
                        reason=message,
                        status=ValidationStatus.MISSING,
                        affected_geographies=slugs,
                    )
                )
                for geography in geographies:
                    result.items.append(
                        _missing_item(
                            metric,
                            geography,
                            message,
                            call_obj.call_id if call_obj else None,
                        )
                    )

    log_event(
        logger,
        logging.INFO,
        "evidence_fetched",
        metrics=len(metrics),
        geographies=len(geographies),
        items=len(result.items),
        usable=sum(1 for item in result.items if item.is_usable),
        calls=len(result.calls),
        errors=len(result.errors),
    )
    return result


def new_package_id() -> str:
    return f"pkg_{uuid.uuid4().hex[:10]}"
