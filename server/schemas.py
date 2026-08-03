"""Request bodies for the workflow API.

Every body here describes a *transition to attempt*, never a state to install. There is
deliberately no endpoint that accepts an ``AnalysisPlanProposal``: the plan is server-held,
and the closest a client can come to changing one is ``EditRequest``, whose fields are
re-validated by ``workflow.edit`` before they take effect.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DescribeRequest(BaseModel):
    objective: str = Field(min_length=1)
    geographies: list[str] = Field(default_factory=list)
    retailer_type: str | None = None
    store_format: str | None = None
    target_segments: str | None = None
    use_llm: bool = True


class AnswerRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    use_llm: bool = True


class EditRequest(BaseModel):
    """Human edits to a proposal. Each field is optional; omitted means unchanged.

    ``category_weights`` is keyed by category id and need not sum to 1 - the workflow
    renormalizes and records the edit, which is why the raw slider values can be sent
    straight through.
    """

    category_weights: dict[str, float] | None = None
    selected_metric_ids: list[str] | None = None
    geographies: list[str] | None = None


class ApproveRequest(BaseModel):
    note: str | None = None
    use_llm_narrative: bool = True


class RejectRequest(BaseModel):
    note: str | None = None


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1)


class ConfirmRevisionRequest(BaseModel):
    use_llm_narrative: bool = True


class RetailerSimulationRunRequest(BaseModel):
    """Explicit scenario inputs. The agent cannot mutate these silently."""

    store_count: int = Field(default=48, ge=1, le=500)
    format_mix: dict[str, float] = Field(
        default_factory=lambda: {"mall": 0.35, "strip": 0.40, "outlet": 0.25}
    )
    seed: int = Field(default=42)
    sales_target_usd: float = Field(default=200_000_000.0, gt=0)
    margin_min_pct: float = Field(default=34.0, ge=0.0, le=100.0)
    margin_max_pct: float = Field(default=42.0, ge=0.0, le=100.0)
    focus_market_id: str | None = Field(
        default=None,
        description=(
            "Optional Atlas slug or county GEOID. When set, the response includes a "
            "similar-market profile of simulated stores in the same public archetype."
        ),
    )


class AnalogMatchingSearchRequest(BaseModel):
    """Search synthetic NorthStar stores for public-market analogs."""

    market_id: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    preferred_format: str | None = None
    scenario: RetailerSimulationRunRequest | None = None


__all__ = [
    "AnswerRequest",
    "ApproveRequest",
    "AssistantRequest",
    "ConfirmRevisionRequest",
    "DescribeRequest",
    "EditRequest",
    "RejectRequest",
    "AnalogMatchingSearchRequest",
    "RetailerSimulationRunRequest",
]
