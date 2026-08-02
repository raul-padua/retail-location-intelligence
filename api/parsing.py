"""Normalize Atlas response bodies into flat, typed observations.

Atlas documents several shapes for the same information: a single-geography response nests
``resultset.data`` directly, a multi-geography response nests ``resultset.geographies[]``,
and a datapoint may carry either ``period``/``value`` or ``periods``/``values``. Every
consumer works off :class:`Observation` instead of reaching into raw JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Observation:
    """One datapoint value for one geography at one period."""

    geography: str
    datapoint: str
    value: float | str | None
    period: str | None
    source: str | None
    reported_geography: str | None
    """The geography Atlas attributed the value to. Differs when context shifts."""

    collection: str | None = None
    item: str | None = None
    """Set for collection observations, e.g. the NAICS code within ``ind.cbp.naics``."""

    @property
    def qualified_datapoint(self) -> str:
        """Identifier that distinguishes items within the same collection datapoint."""
        return f"{self.datapoint}[{self.item}]" if self.item else self.datapoint


@dataclass
class ParsedResponse:
    observations: list[Observation] = field(default_factory=list)
    datapoint_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    geography_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

    def latest(
        self, geography: str, datapoint: str, item: str | None = None
    ) -> Observation | None:
        """Most recent observation for a geography/datapoint pair, if any."""
        matches = [
            observation
            for observation in self.observations
            if observation.geography == geography
            and observation.datapoint == datapoint
            and observation.item == item
        ]
        if not matches:
            return None
        return max(matches, key=lambda observation: observation.period or "")

    def periods_for(self, datapoint: str) -> list[str]:
        return sorted(
            {
                observation.period
                for observation in self.observations
                if observation.datapoint == datapoint and observation.period
            }
        )


class MalformedAtlasResponse(ValueError):
    """Raised when a body cannot be interpreted as a documented Atlas response."""


def _coerce_number(value: Any) -> float | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"na", "n/a", "null", "-"}:
            return None
        cleaned = stripped.replace(",", "").replace("$", "").replace("%", "")
        try:
            return float(cleaned)
        except ValueError:
            return stripped
    return None


def _pairs(entry: dict[str, Any]) -> list[tuple[str | None, Any]]:
    """Zip an entry's periods to its values, tolerating the singular and plural forms."""
    if "values" in entry or "periods" in entry:
        periods = entry.get("periods") or []
        values = entry.get("values") or []
        if not isinstance(periods, list):
            periods = [periods]
        if not isinstance(values, list):
            values = [values]
        if not periods:
            return [(None, value) for value in values]
        if len(values) == 1 and len(periods) > 1:
            return [(str(periods[-1]), values[0])]
        return [
            (str(period) if period is not None else None, value)
            for period, value in zip(periods, values)
        ]
    return [(_as_period(entry.get("period")), entry.get("value"))]


def _as_period(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[-1]) if value else None
    return str(value)


def _parse_collection_block(
    entry: dict[str, Any],
    geography: str,
    parsed: ParsedResponse,
    inherited_geography: str,
) -> None:
    collection = entry.get("collection")
    if not isinstance(collection, str):
        return
    # A collection carries its own geography when Atlas had to widen the context, e.g.
    # county-level business patterns answered for a city request.
    reported_geography = str(entry.get("geography") or inherited_geography)

    for item_entry in entry.get("items", []) or []:
        if not isinstance(item_entry, dict):
            continue
        item = item_entry.get("item")
        item_period = _as_period(item_entry.get("period"))
        for datapoint_entry in item_entry.get("data", []) or []:
            if not isinstance(datapoint_entry, dict):
                continue
            if "collection" in datapoint_entry:
                _parse_collection_block(
                    datapoint_entry, geography, parsed, reported_geography
                )
                continue
            datapoint = datapoint_entry.get("datapoint")
            if not isinstance(datapoint, str):
                continue
            source = datapoint_entry.get("source") or entry.get("source")
            for period, raw_value in _pairs(datapoint_entry):
                parsed.observations.append(
                    Observation(
                        geography=geography,
                        datapoint=datapoint,
                        value=_coerce_number(raw_value),
                        period=period or item_period,
                        source=str(source) if source is not None else None,
                        reported_geography=reported_geography,
                        collection=collection,
                        item=str(item) if item is not None else None,
                    )
                )


def _parse_data_block(
    data: list[Any],
    geography: str,
    parsed: ParsedResponse,
) -> None:
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if "collection" in entry:
            _parse_collection_block(entry, geography, parsed, geography)
            continue
        datapoint = entry.get("datapoint")
        if not isinstance(datapoint, str):
            continue
        reported_geography = entry.get("geography") or geography
        source = entry.get("source")
        for period, raw_value in _pairs(entry):
            parsed.observations.append(
                Observation(
                    geography=geography,
                    datapoint=datapoint,
                    value=_coerce_number(raw_value),
                    period=period,
                    source=str(source) if source is not None else None,
                    reported_geography=str(reported_geography),
                )
            )


def parse_getdata(body: dict[str, Any]) -> ParsedResponse:
    """Parse a ``/getdata`` body into observations plus metadata."""
    if not isinstance(body, dict):
        raise MalformedAtlasResponse("Atlas response must be a JSON object.")

    resultset = body.get("resultset")
    if not isinstance(resultset, dict):
        raise MalformedAtlasResponse("Atlas response is missing a 'resultset' object.")

    parsed = ParsedResponse()

    if isinstance(resultset.get("geographies"), list):
        for block in resultset["geographies"]:
            if not isinstance(block, dict):
                continue
            geography = block.get("geography")
            if not isinstance(geography, str):
                raise MalformedAtlasResponse("A geography block is missing its 'geography' key.")
            data = block.get("data")
            if not isinstance(data, list):
                raise MalformedAtlasResponse(f"Geography block {geography!r} is missing 'data'.")
            _parse_data_block(data, geography, parsed)
    elif isinstance(resultset.get("data"), list):
        geography = resultset.get("geography")
        if not isinstance(geography, str):
            raise MalformedAtlasResponse("Single-geography resultset is missing 'geography'.")
        _parse_data_block(resultset["data"], geography, parsed)
    else:
        raise MalformedAtlasResponse("Atlas resultset contains neither 'geographies' nor 'data'.")

    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        if isinstance(metadata.get("datapoints"), dict):
            parsed.datapoint_metadata = {
                key: value
                for key, value in metadata["datapoints"].items()
                if isinstance(value, dict)
            }
        if isinstance(metadata.get("geographies"), dict):
            parsed.geography_metadata = {
                key: value
                for key, value in metadata["geographies"].items()
                if isinstance(value, dict)
            }

    return parsed
