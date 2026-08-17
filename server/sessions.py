"""Server-held workflow sessions.

Splitting the UI off into a browser creates one problem Streamlit did not have. In the
Streamlit build the ``WorkflowState`` lived in the server process and the user could only
reach it through the transition functions, so ``PlanStatus.APPROVED`` was unforgeable by
construction. Over HTTP, a frontend that posted its state back would hand any caller with
curl the ability to submit ``{"status": "approved"}`` and walk past the gate the entire
architecture is built on.

So the client never holds a plan. It holds an opaque session id, and every endpoint is a
request for a *transition* that the server applies to state only it can see. The approval
gate stays exactly where it was.

Sessions are kept for ``RLI_SESSION_TTL_SECONDS`` (default two hours) from last touch, and
optionally snapshotted under ``RLI_SESSION_DIR`` so a process recycle on the same host can
reload them. That is still not multi-replica shared storage; see
``docs/productionization.md``.
"""

from __future__ import annotations

import os
import pickle
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from orchestration.workflow import WorkflowState

SESSION_LIMIT = 64
"""Oldest sessions are evicted past this. A demo server should not grow without bound."""

DEFAULT_SESSION_TTL_SECONDS = 2 * 60 * 60
"""Two hours from last touch — longer than a typical demo or review meeting."""


def session_ttl_seconds() -> int:
    raw = os.getenv("RLI_SESSION_TTL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SESSION_TTL_SECONDS
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_SESSION_TTL_SECONDS


def session_dir() -> Path | None:
    """Directory for durable session snapshots, or ``None`` to stay memory-only.

    Persistence is **opt-in** via ``RLI_SESSION_DIR``. The default is memory-only because
    ``WorkflowState`` embeds parameterized Pydantic models that are not reliably
    pickleable, and a failed snapshot must never break describe/approve. The two-hour TTL
    plus the client's heartbeat keep demos alive on a warm process without disk.
    """
    if "RLI_SESSION_DIR" not in os.environ:
        return None
    configured = os.environ["RLI_SESSION_DIR"].strip()
    if not configured:
        return None
    return Path(configured)


class UnknownSessionError(KeyError):
    """The session id is not one we issued, or it has been evicted / expired."""


@dataclass
class Session:
    session_id: str
    state: WorkflowState
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    touched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    chat: list[dict] = field(default_factory=list)
    """Assistant transcript. Server-held so a reload does not lose the conversation."""

    retailer_simulation: dict | None = None
    """Last explicit NorthStar simulation run for this session (wire projection)."""

    analog_matching: dict | None = None
    """Last analog-store search for this session (wire projection)."""

    lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)
    """Serializes work on *this* session. See ``SessionStore`` for why it is not shared."""

    def is_expired(self, *, now: datetime | None = None, ttl_seconds: int | None = None) -> bool:
        age = (now or datetime.now(UTC)) - self.touched_at
        return age > timedelta(
            seconds=ttl_seconds if ttl_seconds is not None else session_ttl_seconds()
        )


class SessionStore:
    """A bounded, thread-safe map of session id to workflow state.

    Uvicorn runs request handlers in a thread pool, so two requests against the same
    session can genuinely overlap. Locking is not decoration: without it, a double-clicked
    approve button could run the pipeline twice against the same plan and append two
    versions for one human decision.

    There are two locks, and the distinction matters. ``_lock`` guards the map itself and is
    only ever held for a dictionary operation. Each session then carries its own lock, held
    for the length of a whole transition - which can mean several seconds of Atlas calls, or
    an LLM round trip. A single shared lock would be correct but would serialize the entire
    server behind whichever session was slowest, and the symptom is indistinguishable from
    the API being down.

    Lock ordering is always session-then-map, never the reverse, so the two cannot deadlock.
    """

    def __init__(
        self,
        limit: int = SESSION_LIMIT,
        *,
        ttl_seconds: int | None = None,
        persist_dir: Path | None | object = ...,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self._limit = limit
        self._ttl_seconds = (
            session_ttl_seconds() if ttl_seconds is None else max(60, ttl_seconds)
        )
        self._persist_dir_override = persist_dir

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def _resolve_persist_dir(self) -> Path | None:
        if self._persist_dir_override is ...:
            path = session_dir()
        else:
            path = self._persist_dir_override  # type: ignore[assignment]
        if path is not None:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def create(self) -> Session:
        with self._lock:
            self._purge_expired_locked()
            self._evict_if_full()
            session_id = secrets.token_urlsafe(16)
            session = Session(session_id=session_id, state=WorkflowState())
            self._sessions[session_id] = session
            self._persist_locked(session)
            return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = self._load_locked(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            if session.is_expired(ttl_seconds=self._ttl_seconds):
                self._forget_locked(session_id)
                raise UnknownSessionError(session_id)
            session.touched_at = datetime.now(UTC)
            self._persist_locked(session)
            return session

    def put(self, session_id: str, state: WorkflowState) -> Session:
        with self._lock:
            session = self._lookup_locked(session_id)
            session.state = state
            session.touched_at = datetime.now(UTC)
            self._persist_locked(session)
            return session

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._forget_locked(session_id)

    def lock_for(self, session_id: str) -> threading.RLock:
        """This session's lock, to be held across a whole transition."""
        with self._lock:
            session = self._lookup_locked(session_id)
            return session.lock

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def _lookup_locked(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            session = self._load_locked(session_id)
        if session is None:
            raise UnknownSessionError(session_id)
        if session.is_expired(ttl_seconds=self._ttl_seconds):
            self._forget_locked(session_id)
            raise UnknownSessionError(session_id)
        return session

    def _evict_if_full(self) -> None:
        """Drop least-recently-touched sessions, skipping any mid-request.

        Evicting a session whose transition is in flight would make its own ``put`` fail
        with "unknown session", which is a confusing way to report that the server was
        busy. Overshooting the cap by the number of concurrent requests is the cheaper
        mistake.

        This is the one place that reaches for a session lock while holding the map lock,
        against the ordering rule above. It is safe only because the acquisition is
        non-blocking: a contended lock reports "busy" and is skipped rather than waited on,
        so there is no cycle to deadlock in.
        """
        while len(self._sessions) >= self._limit:
            idle = [
                session
                for session in self._sessions.values()
                if session.lock.acquire(blocking=False)
            ]
            for session in idle:
                session.lock.release()
            if not idle:
                return
            oldest = min(idle, key=lambda entry: entry.touched_at)
            self._forget_locked(oldest.session_id)

    def _purge_expired_locked(self) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.is_expired(ttl_seconds=self._ttl_seconds)
        ]
        for session_id in expired:
            self._forget_locked(session_id)

    def _persist_path(self, session_id: str) -> Path | None:
        persist_dir = self._resolve_persist_dir()
        if persist_dir is None:
            return None
        # Session ids are url-safe tokens; still confine to a single path segment.
        safe = session_id.replace("/", "_").replace("..", "_")
        return persist_dir / f"{safe}.pkl"

    def _persist_locked(self, session: Session) -> None:
        path = self._persist_path(session.session_id)
        if path is None:
            return
        payload = {
            "session_id": session.session_id,
            "state": session.state,
            "created_at": session.created_at,
            "touched_at": session.touched_at,
            "chat": session.chat,
            "retailer_simulation": session.retailer_simulation,
            "analog_matching": session.analog_matching,
        }
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
            tmp.replace(path)
        except Exception:
            # Persistence is best-effort. WorkflowState can contain parameterized Pydantic
            # generics (e.g. Attributed[str]) that pickle cannot round-trip; failing the
            # request would turn a durable-cache miss into a 500 on describe/approve.
            path.unlink(missing_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.unlink(missing_ok=True)

    def _load_locked(self, session_id: str) -> Session | None:
        path = self._persist_path(session_id)
        if path is None or not path.is_file():
            return None
        try:
            payload = pickle.loads(path.read_bytes())
        except Exception:
            path.unlink(missing_ok=True)
            return None
        session = Session(
            session_id=payload["session_id"],
            state=payload["state"],
            created_at=payload["created_at"],
            touched_at=payload["touched_at"],
            chat=list(payload.get("chat") or []),
            retailer_simulation=payload.get("retailer_simulation"),
            analog_matching=payload.get("analog_matching"),
        )
        if session.is_expired(ttl_seconds=self._ttl_seconds):
            path.unlink(missing_ok=True)
            return None
        self._sessions[session_id] = session
        return session

    def _forget_locked(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        path = self._persist_path(session_id)
        if path is not None:
            path.unlink(missing_ok=True)


_store = SessionStore()


def get_store() -> SessionStore:
    return _store


__all__ = [
    "Session",
    "SessionStore",
    "UnknownSessionError",
    "get_store",
    "session_ttl_seconds",
    "DEFAULT_SESSION_TTL_SECONDS",
]
