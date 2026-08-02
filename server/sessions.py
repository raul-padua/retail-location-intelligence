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

The store is in-memory and per-process, which matches the prototype's existing guarantee
that plan lineage does not survive a restart. Nothing here is a substitute for the
persistence a real deployment would need; see ``docs/productionization.md``.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from orchestration.workflow import WorkflowState

SESSION_LIMIT = 64
"""Oldest sessions are evicted past this. A demo server should not grow without bound."""


class UnknownSessionError(KeyError):
    """The session id is not one we issued, or it has been evicted."""


@dataclass
class Session:
    session_id: str
    state: WorkflowState
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    touched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    chat: list[dict] = field(default_factory=list)
    """Assistant transcript. Server-held so a reload does not lose the conversation."""

    lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)
    """Serializes work on *this* session. See ``SessionStore`` for why it is not shared."""


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

    def __init__(self, limit: int = SESSION_LIMIT) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self._limit = limit

    def create(self) -> Session:
        with self._lock:
            self._evict_if_full()
            session_id = secrets.token_urlsafe(16)
            session = Session(session_id=session_id, state=WorkflowState())
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            session.touched_at = datetime.now(UTC)
            return session

    def put(self, session_id: str, state: WorkflowState) -> Session:
        with self._lock:
            session = self.get(session_id)
            session.state = state
            session.touched_at = datetime.now(UTC)
            return session

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def lock_for(self, session_id: str) -> threading.RLock:
        """This session's lock, to be held across a whole transition."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            return session.lock

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

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
            del self._sessions[oldest.session_id]


_store = SessionStore()


def get_store() -> SessionStore:
    return _store


__all__ = ["Session", "SessionStore", "UnknownSessionError", "get_store"]
