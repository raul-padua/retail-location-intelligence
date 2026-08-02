"""The business decision, before it becomes an analysis.

A retail strategy arrives as a sentence, not as a configuration. Turning it into weights
and metric ids necessarily involves inference, and inference is where a planner can
quietly manufacture a decision the executive never made: reading "targeting families"
and silently concluding "suburban full-price format, five-year lease, growth-weighted".

So every field on the profile carries its own provenance. A value the user stated and a
value the planner guessed are different kinds of thing and are never merged into one
undifferentiated struct. A field nobody has established stays :attr:`Provenance.UNKNOWN`
rather than being filled with a plausible default, because a disclosed unknown can be
asked about and a silent assumption cannot.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Provenance(StrEnum):
    """Where a field's value came from. Never inferred from the value itself."""

    USER_SUPPLIED = "user_supplied"
    """Stated explicitly by the user, in the objective text or a clarification answer."""

    PLANNER_INFERRED = "planner_inferred"
    """Derived by the planner. Legitimate, but it is an assumption and is disclosed."""

    UNKNOWN = "unknown"
    """Not established, and potentially material. Never converted into an assumption."""

    UNSUPPORTED = "unsupported"
    """The user asked for it and no available data can express it."""


PROVENANCE_LABELS: dict[Provenance, str] = {
    Provenance.USER_SUPPLIED: "You told us",
    Provenance.PLANNER_INFERRED: "Assumed by the planner",
    Provenance.UNKNOWN: "Not established",
    Provenance.UNSUPPORTED: "Cannot be supported by the available data",
}


class Attributed(BaseModel, Generic[T]):
    """A profile value together with how it came to be set."""

    model_config = {"frozen": True}

    value: T | None = None
    provenance: Provenance = Provenance.UNKNOWN
    note: str | None = Field(
        default=None,
        description="Why the planner inferred this, or what makes the gap material",
    )

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.provenance in {
            Provenance.USER_SUPPLIED,
            Provenance.PLANNER_INFERRED,
        }

    @property
    def is_assumption(self) -> bool:
        return self.provenance == Provenance.PLANNER_INFERRED and self.value is not None

    def describe(self) -> str:
        if self.value is None:
            return PROVENANCE_LABELS[self.provenance]
        rendered = ", ".join(str(entry) for entry in self.value) if isinstance(
            self.value, list
        ) else str(self.value)
        return rendered

    @classmethod
    def from_user(cls, value: T, note: str | None = None) -> Attributed[T]:
        return cls(value=value, provenance=Provenance.USER_SUPPLIED, note=note)

    @classmethod
    def inferred(cls, value: T, note: str) -> Attributed[T]:
        """Inference always carries a reason; there is no inferred value without one."""
        return cls(value=value, provenance=Provenance.PLANNER_INFERRED, note=note)

    @classmethod
    def unknown(cls, note: str | None = None) -> Attributed[T]:
        return cls(value=None, provenance=Provenance.UNKNOWN, note=note)

    @classmethod
    def unsupported(cls, value: T | None = None, note: str | None = None) -> Attributed[T]:
        return cls(value=value, provenance=Provenance.UNSUPPORTED, note=note)


class RetailStrategyProfile(BaseModel):
    """The decision being made, as far as it is currently established.

    Deliberately generic. A GAP-like national apparel retailer is the illustrative
    scenario used throughout the product; nothing here asserts that any named retailer is
    a customer or that proprietary retailer data is available.
    """

    model_config = {"frozen": True}

    retailer_type: Attributed[str] = Field(default_factory=Attributed[str])
    store_format: Attributed[str] = Field(default_factory=Attributed[str])
    target_customer_segments: Attributed[list[str]] = Field(
        default_factory=Attributed[list[str]]
    )
    strategic_priorities: Attributed[list[str]] = Field(
        default_factory=Attributed[list[str]]
    )
    secondary_priorities: Attributed[list[str]] = Field(
        default_factory=Attributed[list[str]]
    )
    hard_constraints: Attributed[list[str]] = Field(default_factory=Attributed[list[str]])
    preferred_market_type: Attributed[str] = Field(default_factory=Attributed[str])
    trade_area_definition: Attributed[str] = Field(default_factory=Attributed[str])
    risk_tolerance: Attributed[str] = Field(default_factory=Attributed[str])
    requested_dimensions: Attributed[list[str]] = Field(
        default_factory=Attributed[list[str]]
    )
    notes: str | None = None

    def fields_by_provenance(self, provenance: Provenance) -> dict[str, Attributed]:
        return {
            name: value
            for name, value in self._attributed_fields().items()
            if value.provenance == provenance
        }

    def assumptions(self) -> dict[str, Attributed]:
        return self.fields_by_provenance(Provenance.PLANNER_INFERRED)

    def unknowns(self) -> dict[str, Attributed]:
        return self.fields_by_provenance(Provenance.UNKNOWN)

    def unsupported(self) -> dict[str, Attributed]:
        return self.fields_by_provenance(Provenance.UNSUPPORTED)

    def _attributed_fields(self) -> dict[str, Attributed]:
        return {
            name: value
            for name, value in self
            if isinstance(value, Attributed)
        }


PROFILE_FIELD_LABELS: dict[str, str] = {
    "retailer_type": "Retailer type",
    "store_format": "Store format",
    "target_customer_segments": "Target customer segments",
    "strategic_priorities": "Strategic priorities",
    "secondary_priorities": "Secondary priorities",
    "hard_constraints": "Hard constraints",
    "preferred_market_type": "Preferred market type",
    "trade_area_definition": "Trade-area definition",
    "risk_tolerance": "Risk tolerance",
    "requested_dimensions": "Dimensions you asked for",
}
