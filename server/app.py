"""HTTP API over the governed workflow.

This is a transport, not a layer of logic. Each endpoint resolves a session, calls exactly
one transition from ``orchestration/workflow.py``, stores the result, and projects it. The rules
about what may follow what stay in the state machine, so the guarantees the test suite
already asserts hold whether the caller is Streamlit, Next.js, or curl.

Two things are worth reading closely, because both are load-bearing for safety:

*Credentials.* The OpenAI key arrives per request in a header and is used to build a
``Settings`` copy for the life of that request. It is never written to the session, never
logged, and never returned. The Atlas token stays server-side and is never sent to the
browser at all - the client learns only whether one is present.

*Authority.* No endpoint accepts a plan. The client can ask to describe, answer, edit,
approve, reject, or revise; it cannot state what the plan currently *is*. That is what
keeps ``PlanStatus.APPROVED`` unforgeable now that a network sits in the middle.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from api.geographies import DEMO_TOKEN_SCOPE_NOTE
from analog_matching.service import (
    AnalogMatchingService,
    get_analog_matching_service,
    search_view,
)
from market_discovery.geography_bridge import GeographyLevelMismatch
from market_discovery.service import (
    MarketDiscoveryService,
    UnknownMarketError,
    get_market_discovery_service,
)
from retailer_simulation.models import RetailerScenario
from retailer_simulation.service import (
    RetailerSimulationService,
    get_retailer_simulation_service,
)
from orchestration import workflow
from orchestration.workflow import Stage, WorkflowError, WorkflowState
from core.config import MissingTokenError, Settings, get_settings
from core.logging import get_logger, log_event
from explanation.assistant import ask, build_context
from metrics.registry import MetricRegistry, UnverifiedMetricError, get_registry
from models.plan import PlanNotApprovedError
from orchestration.pipeline import AnalysisPipeline
from planning.capabilities import CapabilityRegistry, get_capability_registry
from scoring.sensitivity import build_sensitivity_report
from server.schemas import (
    AnswerRequest,
    ApproveRequest,
    AssistantRequest,
    ConfirmRevisionRequest,
    DescribeRequest,
    EditRequest,
    AnalogMatchingSearchRequest,
    RejectRequest,
    RetailerSimulationRunRequest,
)
from server.sessions import Session, SessionStore, UnknownSessionError, get_store
from server.views import (
    assistant_context_view,
    assistant_reply_view,
    catalog_view,
    result_view,
    sensitivity_view,
    settings_view,
    state_view,
)

logger = get_logger("server")

PipelineFactory = Callable[[Settings], AnalysisPipeline]


def default_pipeline_factory(settings: Settings) -> AnalysisPipeline:
    return AnalysisPipeline(settings=settings)


def get_pipeline_factory() -> PipelineFactory:
    """Overridden in tests to supply a mocked Atlas transport."""
    return default_pipeline_factory


def get_metric_registry() -> MetricRegistry:
    return get_registry()


def get_capabilities() -> CapabilityRegistry:
    return get_capability_registry()


def get_discovery() -> MarketDiscoveryService:
    return get_market_discovery_service()


def get_retailer_simulation() -> RetailerSimulationService:
    return get_retailer_simulation_service()


def get_analog_matching() -> AnalogMatchingService:
    return get_analog_matching_service()


def request_settings(
    x_openai_key: Annotated[str | None, Header()] = None,
    x_openai_model: Annotated[str | None, Header()] = None,
) -> Settings:
    """Build per-request settings from the session key the browser holds in memory.

    The key never touches the session store or a log line. If the header is absent the
    environment value applies, and if neither exists every LLM path falls back to its
    deterministic implementation - which is the behaviour the test suite pins.
    """
    base = get_settings()
    if x_openai_key and x_openai_key.strip():
        return base.with_llm(x_openai_key, x_openai_model)
    if x_openai_model and x_openai_model.strip():
        return base.with_llm(base.openai_api_key, x_openai_model)
    return base


DEFAULT_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def _origin_from_vercel_host(host: str) -> str | None:
    value = host.strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value.rstrip("/")
    return f"https://{value}"


def allowed_origins() -> list[str]:
    """Browser origins permitted to call this API.

    ``RLI_CORS_ORIGINS`` takes a comma-separated list and replaces the default entirely,
    which is what a deployment needs. A wildcard is deliberately not supported: this API
    accepts an OpenAI key in a header, and any origin being able to send one is a
    credential-forwarding hole rather than a convenience.

    When unset, localhost defaults remain, and any Vercel-provided hostnames
    (``VERCEL_URL``, branch URL, production URL) are appended so split frontend/API
    deployments work without a manual CORS edit on every preview.
    """
    configured = os.getenv("RLI_CORS_ORIGINS", "").strip()
    origins = (
        [origin.strip() for origin in configured.split(",") if origin.strip()]
        if configured
        else list(DEFAULT_ORIGINS)
    )
    for key in (
        "VERCEL_URL",
        "VERCEL_BRANCH_URL",
        "VERCEL_PROJECT_PRODUCTION_URL",
    ):
        origin = _origin_from_vercel_host(os.getenv(key, ""))
        if origin:
            origins.append(origin)
    # Preserve order while dropping duplicates.
    return list(dict.fromkeys(origins))


SettingsDep = Annotated[Settings, Depends(request_settings)]
StoreDep = Annotated[SessionStore, Depends(get_store)]
RegistryDep = Annotated[MetricRegistry, Depends(get_metric_registry)]
PipelineDep = Annotated[PipelineFactory, Depends(get_pipeline_factory)]

app = FastAPI(
    title="Retail Location Intelligence API",
    version="0.7.0",
    description=(
        "Governed workflow API. The agent proposes; deterministic services decide; "
        "a human approves before anything runs."
    ),
)

# The browser holds the OpenAI key, so it calls this API directly rather than through a
# Next.js route handler. One less process that could log a credential.
#
# The allowlist is an explicit list rather than a wildcard, and it is configurable because
# the default is only right until someone runs the client on a different port - at which
# point every request fails preflight and the UI reports it as "cannot reach the service",
# which is a genuinely hard error to read backwards.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-OpenAI-Key", "X-OpenAI-Model"],
)


# ------------------------------------------------------------------------- plumbing


def _session(store: SessionStore, session_id: str) -> Session:
    try:
        return store.get(session_id)
    except UnknownSessionError:
        raise _no_such_session() from None


def _no_such_session() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail="No such session. Start a new one; sessions do not survive a restart.",
    )


@contextmanager
def _held(store: SessionStore, session_id: str) -> Iterator[Session]:
    """Hold one session's lock for the length of a request that mutates it.

    Anything touching both the workflow state and the chat transcript needs them to move
    together, so those handlers take this once rather than locking each write separately
    and leaving a window between them.
    """
    try:
        lock = store.lock_for(session_id)
    except UnknownSessionError:
        raise _no_such_session() from None
    with lock:
        yield _session(store, session_id)


def _apply(
    store: SessionStore,
    session_id: str,
    transition: Callable[[WorkflowState], WorkflowState],
) -> dict:
    """Run one transition under the session's lock and project the resulting state.

    Illegal transitions surface as 409 rather than 500: "you cannot approve from the
    clarify stage" is a statement about the workflow, not a server fault, and the UI
    renders it as a message.
    """
    with _held(store, session_id) as session:
        try:
            updated = transition(session.state)
        except WorkflowError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except PlanNotApprovedError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except MissingTokenError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        store.put(session_id, updated)
        return state_view(updated)


# --------------------------------------------------------------------------- system


@app.get("/api/health")
def health(settings: SettingsDep) -> dict:
    from server.sessions import DEFAULT_SESSION_TTL_SECONDS, get_store, session_ttl_seconds

    store = get_store()
    return {
        "status": "ok",
        "settings": settings_view(settings),
        "demo_token_scope_note": DEMO_TOKEN_SCOPE_NOTE,
        "session_ttl_seconds": session_ttl_seconds(),
        "session_ttl_default_seconds": DEFAULT_SESSION_TTL_SECONDS,
        "sessions_open": len(store),
    }


@app.get("/api/catalog")
def catalog(
    registry: RegistryDep,
    capabilities: Annotated[CapabilityRegistry, Depends(get_capabilities)],
) -> dict:
    """Static reference data: metrics, capabilities, categories, presets, examples."""
    try:
        return catalog_view(registry, capabilities)
    except UnverifiedMetricError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


# -------------------------------------------------------------- market discovery


@app.get("/api/market-discovery/artifact")
def market_discovery_artifact(
    discovery: Annotated[MarketDiscoveryService, Depends(get_discovery)],
) -> dict:
    """Metadata for the frozen public-county clustering artifact."""
    return discovery.meta()


@app.get("/api/market-discovery/clusters")
def market_discovery_clusters(
    discovery: Annotated[MarketDiscoveryService, Depends(get_discovery)],
) -> dict:
    return {"clusters": discovery.clusters(), "artifact": discovery.meta()}


@app.get("/api/market-discovery/markets")
def market_discovery_markets(
    discovery: Annotated[MarketDiscoveryService, Depends(get_discovery)],
) -> dict:
    return {"markets": discovery.markets(), "artifact": discovery.meta()}


@app.get("/api/market-discovery/pca")
def market_discovery_pca(
    discovery: Annotated[MarketDiscoveryService, Depends(get_discovery)],
) -> dict:
    return {"points": discovery.pca_points(), "artifact": discovery.meta()}


@app.get("/api/market-discovery/markets/{market_id}")
def market_discovery_market(
    market_id: str,
    discovery: Annotated[MarketDiscoveryService, Depends(get_discovery)],
    peers: int = 5,
) -> dict:
    """County archetype profile. ``market_id`` may be a GEOID or Atlas demo slug."""
    try:
        return discovery.market_profile_view(market_id, peer_count=max(1, min(peers, 20)))
    except GeographyLevelMismatch as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except UnknownMarketError as error:
        raise HTTPException(
            status_code=404,
            detail=f"No market archetype for {market_id!r}.",
        ) from error


# ----------------------------------------------------------- retailer simulation


def _scenario_from_request(body: RetailerSimulationRunRequest) -> RetailerScenario:
    return RetailerScenario(
        store_count=body.store_count,
        format_mix=body.format_mix,
        seed=body.seed,
        sales_target_usd=body.sales_target_usd,
        margin_min_pct=body.margin_min_pct,
        margin_max_pct=body.margin_max_pct,
    )


@app.get("/api/retailer-simulation/meta")
def retailer_simulation_meta(
    simulation: Annotated[RetailerSimulationService, Depends(get_retailer_simulation)],
) -> dict:
    """Simulator version and provenance metadata."""
    return simulation.meta()


@app.get("/api/retailer-simulation/benchmarks")
def retailer_simulation_benchmarks(
    simulation: Annotated[RetailerSimulationService, Depends(get_retailer_simulation)],
) -> dict:
    """Public aggregate anchors with verification states."""
    return simulation.benchmarks()


@app.get("/api/retailer-simulation/defaults")
def retailer_simulation_defaults(
    simulation: Annotated[RetailerSimulationService, Depends(get_retailer_simulation)],
) -> dict:
    scenario = simulation.default_scenario()
    return {"scenario": scenario.model_dump(mode="json")}


@app.post("/api/retailer-simulation/run")
def retailer_simulation_run_stateless(
    body: RetailerSimulationRunRequest,
    simulation: Annotated[RetailerSimulationService, Depends(get_retailer_simulation)],
) -> dict:
    """Run a simulation from explicit scenario parameters (no session storage)."""
    scenario = _scenario_from_request(body)
    return {
        "simulation": simulation.run_view(
            scenario,
            focus_market_id=body.focus_market_id,
        )
    }


@app.get("/api/sessions/{session_id}/retailer-simulation")
def retailer_simulation_last(
    session_id: str,
    store: StoreDep,
) -> dict:
    session = _session(store, session_id)
    if session.retailer_simulation is None:
        raise HTTPException(status_code=404, detail="No simulation has been run in this session.")
    return {"simulation": session.retailer_simulation}


@app.post("/api/sessions/{session_id}/retailer-simulation/run")
def retailer_simulation_run_session(
    session_id: str,
    body: RetailerSimulationRunRequest,
    store: StoreDep,
    simulation: Annotated[RetailerSimulationService, Depends(get_retailer_simulation)],
) -> dict:
    """Run and persist the last simulation for this session."""
    session = _session(store, session_id)
    scenario = _scenario_from_request(body)
    with session.lock:
        payload = simulation.run_view(
            scenario,
            focus_market_id=body.focus_market_id,
        )
        session.retailer_simulation = payload
    return {"simulation": payload}


# ------------------------------------------------------------- analog matching


def _simulation_for_analog_search(
    session: Session | None,
    body: AnalogMatchingSearchRequest,
    simulation_svc: RetailerSimulationService,
) -> SimulationArtifact:
    """Prefer session simulation when scenario matches; otherwise generate."""
    from retailer_simulation.service import artifact_from_wire

    if session is not None and session.retailer_simulation is not None and body.scenario is None:
        return artifact_from_wire(session.retailer_simulation)

    scenario = _scenario_from_request(body.scenario) if body.scenario else None
    chosen = scenario or simulation_svc.default_scenario()

    if session is not None and session.retailer_simulation is not None and body.scenario is not None:
        stored = session.retailer_simulation.get("scenario", {})
        requested = chosen.model_dump()
        reuse_keys = ("store_count", "seed", "sales_target_usd", "margin_min_pct", "margin_max_pct")
        if all(stored.get(key) == requested.get(key) for key in reuse_keys):
            stored_mix = stored.get("format_mix", {})
            if stored_mix == requested.get("format_mix"):
                return artifact_from_wire(session.retailer_simulation)

    return simulation_svc.run(chosen)


@app.get("/api/analog-matching/meta")
def analog_matching_meta(
    matching: Annotated[AnalogMatchingService, Depends(get_analog_matching)],
) -> dict:
    """Matcher version, feature registry, and similarity thresholds."""
    return matching.meta()


@app.post("/api/analog-matching/search")
def analog_matching_search_stateless(
    body: AnalogMatchingSearchRequest,
    matching: Annotated[AnalogMatchingService, Depends(get_analog_matching)],
    simulation: Annotated[RetailerSimulationService, Depends(get_retailer_simulation)],
) -> dict:
    """Run analog search without session storage."""
    try:
        artifact = _simulation_for_analog_search(None, body, simulation)
        result = matching.search(
            market_id=body.market_id,
            simulation=artifact,
            top_k=body.top_k,
            preferred_format=body.preferred_format,
        )
    except GeographyLevelMismatch as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except UnknownMarketError as error:
        raise HTTPException(
            status_code=404,
            detail=f"No market profile for {body.market_id!r}.",
        ) from error
    return {"search": search_view(result)}


@app.get("/api/sessions/{session_id}/analog-matching")
def analog_matching_last(
    session_id: str,
    store: StoreDep,
) -> dict:
    session = _session(store, session_id)
    if session.analog_matching is None:
        raise HTTPException(status_code=404, detail="No analog search has been run in this session.")
    return {"search": session.analog_matching}


@app.post("/api/sessions/{session_id}/analog-matching/search")
def analog_matching_search_session(
    session_id: str,
    body: AnalogMatchingSearchRequest,
    store: StoreDep,
    matching: Annotated[AnalogMatchingService, Depends(get_analog_matching)],
    simulation: Annotated[RetailerSimulationService, Depends(get_retailer_simulation)],
) -> dict:
    """Run and persist the last analog search for this session."""
    session = _session(store, session_id)
    try:
        artifact = _simulation_for_analog_search(session, body, simulation)
        result = matching.search(
            market_id=body.market_id,
            simulation=artifact,
            top_k=body.top_k,
            preferred_format=body.preferred_format,
        )
    except GeographyLevelMismatch as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except UnknownMarketError as error:
        raise HTTPException(
            status_code=404,
            detail=f"No market profile for {body.market_id!r}.",
        ) from error
    payload = search_view(result)
    with session.lock:
        session.analog_matching = payload
    return {"search": payload}


# ------------------------------------------------------------------------- sessions


@app.post("/api/sessions", status_code=201)
def create_session(store: StoreDep) -> dict:
    session = store.create()
    log_event(logger, logging.INFO, "session_created", sessions_open=len(store))
    return {"session_id": session.session_id, "state": state_view(session.state)}


@app.get("/api/sessions/{session_id}")
def read_session(session_id: str, store: StoreDep) -> dict:
    return {"session_id": session_id, "state": state_view(_session(store, session_id).state)}


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, store: StoreDep) -> Response:
    store.drop(session_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------- transitions


@app.post("/api/sessions/{session_id}/describe")
def describe(
    session_id: str,
    body: DescribeRequest,
    store: StoreDep,
    settings: SettingsDep,
    registry: RegistryDep,
) -> dict:
    return _apply(
        store,
        session_id,
        lambda state: workflow.describe(
            state,
            body.objective,
            body.geographies,
            retailer_type=body.retailer_type,
            store_format=body.store_format,
            target_segments=body.target_segments,
            settings=settings,
            registry=registry,
            use_llm=body.use_llm and settings.llm_enabled,
        ),
    )


@app.post("/api/sessions/{session_id}/answer")
def answer(
    session_id: str,
    body: AnswerRequest,
    store: StoreDep,
    settings: SettingsDep,
    registry: RegistryDep,
) -> dict:
    return _apply(
        store,
        session_id,
        lambda state: workflow.answer(
            state,
            body.answers,
            settings=settings,
            registry=registry,
            use_llm=body.use_llm and settings.llm_enabled,
        ),
    )


@app.post("/api/sessions/{session_id}/edit")
def edit(
    session_id: str, body: EditRequest, store: StoreDep, registry: RegistryDep
) -> dict:
    weights = None
    if body.category_weights is not None:
        from models.metrics import MetricCategory

        try:
            weights = {
                MetricCategory(key): value for key, value in body.category_weights.items()
            }
        except ValueError as error:
            raise HTTPException(status_code=422, detail=f"Unknown category: {error}") from error

    return _apply(
        store,
        session_id,
        lambda state: workflow.edit(
            state,
            category_weights=weights,
            selected_metric_ids=body.selected_metric_ids,
            geographies=body.geographies,
            registry=registry,
        ),
    )


@app.post("/api/sessions/{session_id}/approve")
def approve(
    session_id: str,
    body: ApproveRequest,
    store: StoreDep,
    settings: SettingsDep,
    pipeline_factory: PipelineDep,
) -> dict:
    return _apply(
        store,
        session_id,
        lambda state: workflow.approve_and_run(
            state,
            pipeline_factory(settings),
            note=body.note,
            use_llm_narrative=body.use_llm_narrative and settings.llm_enabled,
        ),
    )


@app.post("/api/sessions/{session_id}/reject")
def reject(session_id: str, body: RejectRequest, store: StoreDep) -> dict:
    return _apply(store, session_id, lambda state: workflow.reject(state, note=body.note))


@app.post("/api/sessions/{session_id}/reset")
def reset(session_id: str, store: StoreDep) -> dict:
    """Start over: clear the workflow and the transcript as one step.

    Held under a single lock because a reset that clears the plan but leaves the previous
    conversation attached is worse than either half - the assistant would be answering
    about an analysis that no longer exists.
    """
    with _held(store, session_id):
        _apply(store, session_id, workflow.reset)
        session = _session(store, session_id)
        session.chat.clear()
        return state_view(session.state)


@app.post("/api/sessions/{session_id}/back-to-questions")
def back_to_questions(session_id: str, store: StoreDep) -> dict:
    """Return to the clarify stage from review, so an answer can be revised.

    Legal because ``CLARIFY`` is strictly less permissive than ``REVIEW``: the move gives
    up the ability to approve, it does not acquire anything.
    """
    from dataclasses import replace as dataclass_replace

    def transition(state: WorkflowState) -> WorkflowState:
        if state.stage != Stage.REVIEW or state.plan is None:
            raise WorkflowError("There are no questions to go back to.")
        if not state.plan.clarification_questions:
            raise WorkflowError("This plan has no clarification questions.")
        return dataclass_replace(state, stage=Stage.CLARIFY)

    return _apply(store, session_id, transition)


# ------------------------------------------------------------------------ revisions


@app.post("/api/sessions/{session_id}/revision/confirm")
def confirm_revision(
    session_id: str,
    body: ConfirmRevisionRequest,
    store: StoreDep,
    settings: SettingsDep,
    registry: RegistryDep,
    pipeline_factory: PipelineDep,
) -> dict:
    return _apply(
        store,
        session_id,
        lambda state: workflow.confirm_revision(
            state,
            pipeline_factory(settings),
            registry=registry,
            use_llm_narrative=body.use_llm_narrative and settings.llm_enabled,
        ),
    )


@app.post("/api/sessions/{session_id}/revision/discard")
def discard_revision(session_id: str, store: StoreDep) -> dict:
    return _apply(store, session_id, workflow.discard_revision)


# ------------------------------------------------------------------------ assistant


@app.get("/api/sessions/{session_id}/assistant")
def assistant_state(
    session_id: str, store: StoreDep, settings: SettingsDep, registry: RegistryDep
) -> dict:
    session = _session(store, session_id)
    context = build_context(
        registry,
        settings,
        session.state.result,
        scope_note=DEMO_TOKEN_SCOPE_NOTE,
        plan=session.state.plan if session.state.stage == Stage.EXECUTED else None,
        analog_search=session.analog_matching,
    )
    return {
        "messages": list(session.chat),
        "context": assistant_context_view(context),
        "llm_enabled": settings.llm_enabled,
    }


@app.post("/api/sessions/{session_id}/assistant")
def assistant_ask(
    session_id: str,
    body: AssistantRequest,
    store: StoreDep,
    settings: SettingsDep,
    registry: RegistryDep,
) -> dict:
    """Answer a question, and park a revision proposal if the message asked for one.

    Parking is the whole point. An actionable revision is written to the session as
    ``pending_revision`` and nothing else happens: no rerun, no weight change, no new
    version. It sits there until a separate confirm call arrives.
    """
    from dataclasses import replace as dataclass_replace

    with _held(store, session_id) as session:
        state = session.state
        executed = state.stage == Stage.EXECUTED

        context = build_context(
            registry,
            settings,
            state.result,
            scope_note=DEMO_TOKEN_SCOPE_NOTE,
            plan=state.plan if executed else None,
            analog_search=session.analog_matching,
        )
        history = [(entry["role"], entry["content"]) for entry in session.chat]
        reply = ask(
            body.message,
            context,
            settings,
            history=history,
            plan=state.plan if executed else None,
        )

        session.chat.append({"role": "user", "content": body.message})
        session.chat.append(
            {
                "role": "assistant",
                "content": reply.text,
                "generated_by": reply.generated_by,
                "refused": reply.refused,
                "notes": list(reply.notes),
            }
        )

        if reply.revision is not None and reply.revision.changed_fields:
            store.put(session_id, dataclass_replace(state, pending_revision=reply.revision))

        return {
            "reply": assistant_reply_view(reply),
            "messages": list(session.chat),
            "state": state_view(store.get(session_id).state),
        }


@app.delete("/api/sessions/{session_id}/assistant")
def clear_assistant(session_id: str, store: StoreDep) -> dict:
    with _held(store, session_id) as session:
        session.chat.clear()
        return {"messages": list(session.chat)}


# -------------------------------------------------------------------------- results


@app.get("/api/sessions/{session_id}/sensitivity")
def sensitivity(session_id: str, store: StoreDep) -> dict:
    """Deterministic strategy-lens comparison over the evidence already retrieved.

    No Atlas call and no model: this re-scores values that are already in hand, which is
    why it can be a plain GET.
    """
    state = _session(store, session_id).state
    current = state.current
    if current is None or current.result.evidence is None:
        raise HTTPException(status_code=409, detail="No executed analysis to analyse.")

    evidence = current.result.evidence
    # Metric definitions come off the evidence items rather than the registry so that any
    # per-metric weight override carried by the approved plan is respected.
    metrics = {item.metric.metric_id: item.metric for item in evidence.items}
    report = build_sensitivity_report(evidence, metrics, current.plan.category_weights)
    return sensitivity_view(report)


@app.get("/api/sessions/{session_id}/result")
def full_result(session_id: str, store: StoreDep, version: int | None = None) -> dict:
    """The complete result including raw Atlas bodies. Backs the evidence panel and export."""
    state = _session(store, session_id).state
    if not state.history:
        raise HTTPException(status_code=409, detail="No executed analysis yet.")

    chosen = state.history[-1]
    if version is not None:
        matches = [entry for entry in state.history if entry.plan.version == version]
        if not matches:
            raise HTTPException(status_code=404, detail=f"No version {version}.")
        chosen = matches[0]

    return {
        "version": chosen.plan.version,
        "result": result_view(chosen.result, include_raw_calls=True),
    }


__all__ = ["app", "get_pipeline_factory", "request_settings"]
