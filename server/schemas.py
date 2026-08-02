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


__all__ = [
    "AnswerRequest",
    "ApproveRequest",
    "AssistantRequest",
    "ConfirmRevisionRequest",
    "DescribeRequest",
    "EditRequest",
    "RejectRequest",
]
