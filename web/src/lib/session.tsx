"use client";

/**
 * The single place that owns client state.
 *
 * There is deliberately very little of it. The workflow state is whatever the server last
 * returned, and every action is a round trip - no optimistic updates, no local mutation of
 * a plan. That costs a few milliseconds and buys the guarantee that the screen can never
 * show an approval the server did not grant.
 *
 * The OpenAI key is the one genuinely client-owned value, and it is held in a React ref
 * and state rather than `localStorage` so that closing the tab disposes of it.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, api, type Credentials, type DescribeInput } from "./api";
import type { Catalog, ServerSettings, WorkflowState } from "./types";

interface SessionValue {
  sessionId: string | null;
  state: WorkflowState | null;
  catalog: Catalog | null;
  settings: ServerSettings | null;
  booting: boolean;
  busy: boolean;
  error: string | null;
  bootError: string | null;

  openaiKey: string;
  model: string;
  useLlm: boolean;
  llmAvailable: boolean;

  setOpenaiKey: (value: string) => void;
  setModel: (value: string) => void;
  setUseLlm: (value: boolean) => void;
  dismissError: () => void;

  describe: (input: Omit<DescribeInput, "useLlm">) => Promise<void>;
  answer: (answers: Record<string, string>) => Promise<void>;
  edit: (edits: {
    categoryWeights?: Record<string, number>;
    selectedMetricIds?: string[];
    geographies?: string[];
  }) => Promise<void>;
  approve: () => Promise<void>;
  reject: (note?: string) => Promise<void>;
  reset: () => Promise<void>;
  backToQuestions: () => Promise<void>;
  confirmRevision: () => Promise<void>;
  discardRevision: () => Promise<void>;
  applyState: (next: WorkflowState) => void;
  credentials: Credentials;
}

const SessionContext = createContext<SessionValue | null>(null);

const SESSION_STORAGE_KEY = "rli.session_id";
/** Keep the server session warm during long demos (server TTL defaults to two hours). */
const SESSION_HEARTBEAT_MS = 2 * 60 * 1000;

function readStoredSessionId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredSessionId(sessionId: string | null): void {
  try {
    if (sessionId) sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    else sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Private mode / disabled storage — session still works for the tab lifetime.
  }
}

async function bootSession(): Promise<{ session_id: string; state: WorkflowState }> {
  const existing = readStoredSessionId();
  if (existing) {
    try {
      return await api.readSession(existing);
    } catch (caught) {
      if (!(caught instanceof ApiError && caught.isMissingSession)) {
        throw caught;
      }
      writeStoredSessionId(null);
    }
  }
  const created = await api.createSession();
  writeStoredSessionId(created.session_id);
  return created;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState<WorkflowState | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [settings, setSettings] = useState<ServerSettings | null>(null);
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const [openaiKey, setOpenaiKey] = useState("");
  const [model, setModel] = useState("");
  const [useLlm, setUseLlm] = useState(true);

  const credentials = useMemo<Credentials>(
    () => ({ openaiKey: openaiKey || null, model: model || null }),
    [openaiKey, model],
  );

  const llmAvailable = Boolean(openaiKey.trim()) || Boolean(settings?.llm_enabled);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [health, loadedCatalog, session] = await Promise.all([
          api.health(),
          api.catalog(),
          bootSession(),
        ]);
        if (cancelled) return;
        setSettings(health.settings);
        setCatalog(loadedCatalog);
        setModel(health.settings.llm_model || health.settings.default_llm_model);
        setSessionId(session.session_id);
        writeStoredSessionId(session.session_id);
        setState(session.state);
      } catch (caught) {
        if (!cancelled) {
          setBootError(
            caught instanceof ApiError ? caught.message : String(caught),
          );
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionId || booting) return;
    const tick = window.setInterval(() => {
      void api.readSession(sessionId).catch((caught) => {
        if (caught instanceof ApiError && caught.isMissingSession) {
          writeStoredSessionId(null);
        }
      });
    }, SESSION_HEARTBEAT_MS);
    return () => window.clearInterval(tick);
  }, [sessionId, booting]);

  /**
   * Run one server transition. A workflow conflict is surfaced as a message and the state
   * is left exactly as the server has it, because a 409 means nothing moved.
   */
  const run = useCallback(
    async (action: (session: string) => Promise<WorkflowState>) => {
      if (!sessionId) return;
      setBusy(true);
      setError(null);
      try {
        setState(await action(sessionId));
      } catch (caught) {
        if (caught instanceof ApiError && caught.isMissingSession) {
          const fresh = await api.createSession();
          writeStoredSessionId(fresh.session_id);
          setSessionId(fresh.session_id);
          setState(fresh.state);
          setError(
            "That session expired after the idle limit (default two hours), so a new one was started.",
          );
        } else {
          setError(caught instanceof Error ? caught.message : String(caught));
        }
      } finally {
        setBusy(false);
      }
    },
    [sessionId],
  );

  const value: SessionValue = {
    sessionId,
    state,
    catalog,
    settings,
    booting,
    busy,
    error,
    bootError,
    openaiKey,
    model,
    useLlm,
    llmAvailable,
    setOpenaiKey,
    setModel,
    setUseLlm,
    dismissError: () => setError(null),
    credentials,

    describe: (input) =>
      run((session) =>
        api.describe(
          session,
          { ...input, useLlm: useLlm && llmAvailable },
          credentials,
        ),
      ),
    answer: (answers) =>
      run((session) =>
        api.answer(session, answers, useLlm && llmAvailable, credentials),
      ),
    edit: (edits) => run((session) => api.edit(session, edits)),
    approve: () =>
      run((session) => api.approve(session, useLlm && llmAvailable, credentials)),
    reject: (note) => run((session) => api.reject(session, note)),
    reset: () => run((session) => api.reset(session)),
    backToQuestions: () => run((session) => api.backToQuestions(session)),
    confirmRevision: () =>
      run((session) =>
        api.confirmRevision(session, useLlm && llmAvailable, credentials),
      ),
    discardRevision: () => run((session) => api.discardRevision(session)),
    applyState: setState,
  };

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used inside a SessionProvider.");
  }
  return value;
}
