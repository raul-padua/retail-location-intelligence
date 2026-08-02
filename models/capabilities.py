"""What the agent is allowed to ask for, and what it must admit it cannot do.

A capability registry exists for the same reason the metric registry does: to make the
agent's action space enumerable. The planner selects capability ids from this list; it
cannot name a function, and there is no path by which a capability id it invented
resolves to executable code.

The unavailable entries matter as much as the available ones. Foot traffic, competitor
locations, and cannibalization are the things a site-selection conversation turns to
within about two minutes, and an agent with no representation of them either stays silent
or improvises. Representing them explicitly - with what data they would need and why this
system cannot execute them - lets the agent recommend them as a next step while making it
structurally unable to behave as though one ran.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    """Implemented, governed, and executable by the pipeline."""

    UNAVAILABLE = "unavailable"
    """Named so the agent can point at it. There is no code path that runs it."""


class CapabilityKind(StrEnum):
    RETRIEVAL = "retrieval"
    VALIDATION = "validation"
    CALCULATION = "calculation"
    EXPLANATION = "explanation"
    MODELLING = "modelling"


class Capability(BaseModel):
    """One analytical operation the agent may request, or must decline."""

    model_config = {"frozen": True}

    capability_id: str
    display_name: str
    kind: CapabilityKind
    status: CapabilityStatus
    description: str

    required_data: list[str] = Field(
        default_factory=list,
        description="Inputs the capability consumes; for unavailable ones, what is missing",
    )
    expected_provider: str | None = Field(
        default=None,
        description="Source or provider type that would supply an unavailable capability",
    )
    unavailable_because: str | None = Field(
        default=None,
        description="Why this system cannot execute it today",
    )
    produces: str | None = Field(
        default=None, description="What an available capability returns"
    )
    deterministic: bool = True
    """Whether the capability's output is reproducible arithmetic rather than prose."""

    @property
    def is_available(self) -> bool:
        return self.status == CapabilityStatus.AVAILABLE

    def describe_for_planner(self) -> str:
        """One line for the planner's capability description. No implementation detail."""
        if self.is_available:
            return (
                f"{self.capability_id}: {self.description} "
                f"Produces: {self.produces or 'a validated result'}."
            )
        return (
            f"{self.capability_id}: UNAVAILABLE. {self.description} "
            f"Cannot run because {self.unavailable_because} "
            f"Would require: {', '.join(self.required_data) or 'additional data'}"
            + (f", from {self.expected_provider}." if self.expected_provider else ".")
        )
