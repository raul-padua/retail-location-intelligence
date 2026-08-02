"""Deterministic normalization primitives.

Pure functions over floats. No I/O, no randomness, no model involvement, so the same
inputs always produce byte-identical outputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.metrics import Direction, Normalization

NEUTRAL_SCORE = 50.0
"""Assigned when every candidate shares the same value: nothing distinguishes them, and a
0 or a 100 would invent a distinction that the data does not support."""


@dataclass(frozen=True)
class NormalizationResult:
    scores: dict[str, float]
    method: Normalization
    direction: Direction
    observed_min: float
    observed_max: float
    detail: str
    """Human-readable statement of exactly what arithmetic was applied."""


def _apply_direction(score: float, direction: Direction) -> float:
    return score if direction == Direction.HIGHER_IS_BETTER else 100.0 - score


def normalize_values(
    values: dict[str, float],
    direction: Direction,
    method: Normalization = Normalization.MIN_MAX,
) -> NormalizationResult:
    """Map raw values to a 0-100 scale where 100 is always the most attractive.

    ``values`` is keyed by geography slug and must contain only usable numbers; missing
    data is handled upstream so that this function never has to guess.
    """
    if not values:
        raise ValueError("normalize_values requires at least one value")

    numbers = list(values.values())
    observed_min = min(numbers)
    observed_max = max(numbers)

    if observed_min == observed_max:
        return NormalizationResult(
            scores={slug: NEUTRAL_SCORE for slug in values},
            method=method,
            direction=direction,
            observed_min=observed_min,
            observed_max=observed_max,
            detail=(
                f"All candidates share the value {observed_min:g}; each is assigned the "
                f"neutral score {NEUTRAL_SCORE:g} because the metric does not differentiate them."
            ),
        )

    if method == Normalization.MIN_MAX:
        span = observed_max - observed_min
        scaled = {slug: (value - observed_min) / span * 100.0 for slug, value in values.items()}
        detail = (
            f"Min-max scaled over the candidate set: (value - {observed_min:g}) / "
            f"{span:g} x 100."
        )
    elif method == Normalization.RANK:
        # Ties share the average of the positions they span, so equal values always receive
        # equal scores and the set still spans 0-100.
        ordered = sorted(values.items(), key=lambda entry: entry[1])
        positions: dict[str, float] = {}
        index = 0
        while index < len(ordered):
            end = index
            while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
                end += 1
            average_position = (index + end) / 2.0
            for slug, _ in ordered[index : end + 1]:
                positions[slug] = average_position
            index = end + 1

        divisor = len(ordered) - 1
        scaled = {slug: position / divisor * 100.0 for slug, position in positions.items()}
        detail = (
            f"Percentile rank within the {len(ordered)} candidate regions, with tied values "
            "sharing an averaged position. Ignores the size of the gaps, so one unusually "
            "large region cannot compress the rest of the field."
        )
    else:
        raise ValueError(f"Unsupported normalization method: {method}")

    oriented = {slug: _apply_direction(score, direction) for slug, score in scaled.items()}
    if direction == Direction.LOWER_IS_BETTER:
        detail += " Inverted because lower values are more attractive for this metric."

    return NormalizationResult(
        scores={slug: round(score, 4) for slug, score in oriented.items()},
        method=method,
        direction=direction,
        observed_min=observed_min,
        observed_max=observed_max,
        detail=detail,
    )
