/**
 * Typed client for the workflow API.
 *
 * The browser talks to FastAPI directly rather than through a Next.js route handler. That
 * is deliberate: the OpenAI key lives in this tab's memory and travels as a request
 * header, and routing it through the Next server would add a second process that could
 * log it. Nothing here writes the key to `localStorage`, a cookie, or the URL.
 */

import type {
  AssistantAskResponse,
  AssistantState,
  ArchetypeCluster,
  ArchetypeMarket,
  Catalog,
  Health,
  MarketArchetypeProfile,
  MarketDiscoveryArtifact,
  PcaPoint,
  RetailerBenchmarkCatalog,
  RetailerSimulationArtifact,
  RetailerSimulationMeta,
  RetailerSimulationRunRequest,
  AnalogMatchingMeta,
  AnalogMatchingSearchRequest,
  AnalogSearchResult,
  SensitivityReport,
  AnalysisResult,
  WorkflowState,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** A 409 is the workflow declining, not the server breaking. Render it, don't alarm. */
  get isWorkflowConflict(): boolean {
    return this.status === 409;
  }

  get isMissingSession(): boolean {
    return this.status === 404;
  }
}

export interface Credentials {
  openaiKey?: string | null;
  model?: string | null;
}

function headers(credentials: Credentials | undefined): HeadersInit {
  const result: Record<string, string> = { "Content-Type": "application/json" };
  if (credentials?.openaiKey?.trim()) {
    result["X-OpenAI-Key"] = credentials.openaiKey.trim();
  }
  if (credentials?.model?.trim()) {
    result["X-OpenAI-Model"] = credentials.model.trim();
  }
  return result;
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; credentials?: Credentials } = {},
): Promise<T> {
  const { method = "GET", body, credentials } = options;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: headers(credentials),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the analysis service at ${API_BASE}. Start it with ` +
        `\`uv run uvicorn server.app:app --port 8000\`.`,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      (payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : null) ?? `Request failed with status ${response.status}.`;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export interface DescribeInput {
  objective: string;
  geographies: string[];
  retailerType?: string | null;
  storeFormat?: string | null;
  targetSegments?: string | null;
  useLlm: boolean;
}

export const api = {
  health: (credentials?: Credentials) =>
    request<Health>("/api/health", { credentials }),

  catalog: () => request<Catalog>("/api/catalog"),

  createSession: () =>
    request<{ session_id: string; state: WorkflowState }>("/api/sessions", {
      method: "POST",
    }),

  readSession: (session: string) =>
    request<{ session_id: string; state: WorkflowState }>(
      `/api/sessions/${session}`,
    ),

  describe: (session: string, input: DescribeInput, credentials?: Credentials) =>
    request<WorkflowState>(`/api/sessions/${session}/describe`, {
      method: "POST",
      credentials,
      body: {
        objective: input.objective,
        geographies: input.geographies,
        retailer_type: input.retailerType || null,
        store_format: input.storeFormat || null,
        target_segments: input.targetSegments || null,
        use_llm: input.useLlm,
      },
    }),

  answer: (
    session: string,
    answers: Record<string, string>,
    useLlm: boolean,
    credentials?: Credentials,
  ) =>
    request<WorkflowState>(`/api/sessions/${session}/answer`, {
      method: "POST",
      credentials,
      body: { answers, use_llm: useLlm },
    }),

  edit: (
    session: string,
    edits: {
      categoryWeights?: Record<string, number>;
      selectedMetricIds?: string[];
      geographies?: string[];
    },
  ) =>
    request<WorkflowState>(`/api/sessions/${session}/edit`, {
      method: "POST",
      body: {
        category_weights: edits.categoryWeights ?? null,
        selected_metric_ids: edits.selectedMetricIds ?? null,
        geographies: edits.geographies ?? null,
      },
    }),

  approve: (session: string, useLlmNarrative: boolean, credentials?: Credentials) =>
    request<WorkflowState>(`/api/sessions/${session}/approve`, {
      method: "POST",
      credentials,
      body: { use_llm_narrative: useLlmNarrative },
    }),

  reject: (session: string, note?: string) =>
    request<WorkflowState>(`/api/sessions/${session}/reject`, {
      method: "POST",
      body: { note: note ?? null },
    }),

  reset: (session: string) =>
    request<WorkflowState>(`/api/sessions/${session}/reset`, { method: "POST" }),

  backToQuestions: (session: string) =>
    request<WorkflowState>(`/api/sessions/${session}/back-to-questions`, {
      method: "POST",
    }),

  confirmRevision: (
    session: string,
    useLlmNarrative: boolean,
    credentials?: Credentials,
  ) =>
    request<WorkflowState>(`/api/sessions/${session}/revision/confirm`, {
      method: "POST",
      credentials,
      body: { use_llm_narrative: useLlmNarrative },
    }),

  discardRevision: (session: string) =>
    request<WorkflowState>(`/api/sessions/${session}/revision/discard`, {
      method: "POST",
    }),

  assistantState: (session: string, credentials?: Credentials) =>
    request<AssistantState>(`/api/sessions/${session}/assistant`, { credentials }),

  ask: (session: string, message: string, credentials?: Credentials) =>
    request<AssistantAskResponse>(`/api/sessions/${session}/assistant`, {
      method: "POST",
      credentials,
      body: { message },
    }),

  clearChat: (session: string) =>
    request<{ messages: [] }>(`/api/sessions/${session}/assistant`, {
      method: "DELETE",
    }),

  sensitivity: (session: string) =>
    request<SensitivityReport>(`/api/sessions/${session}/sensitivity`),

  fullResult: (session: string, version?: number) =>
    request<{ version: number; result: AnalysisResult }>(
      `/api/sessions/${session}/result${version ? `?version=${version}` : ""}`,
    ),

  marketDiscoveryArtifact: () =>
    request<MarketDiscoveryArtifact>("/api/market-discovery/artifact"),

  marketDiscoveryClusters: () =>
    request<{ clusters: ArchetypeCluster[]; artifact: MarketDiscoveryArtifact }>(
      "/api/market-discovery/clusters",
    ),

  marketDiscoveryMarkets: () =>
    request<{ markets: ArchetypeMarket[]; artifact: MarketDiscoveryArtifact }>(
      "/api/market-discovery/markets",
    ),

  marketDiscoveryPca: () =>
    request<{ points: PcaPoint[]; artifact: MarketDiscoveryArtifact }>(
      "/api/market-discovery/pca",
    ),

  marketDiscoveryMarket: (marketId: string, peers = 5) =>
    request<MarketArchetypeProfile>(
      `/api/market-discovery/markets/${encodeURIComponent(marketId)}?peers=${peers}`,
    ),

  retailerSimulationMeta: () =>
    request<RetailerSimulationMeta>("/api/retailer-simulation/meta"),

  retailerSimulationBenchmarks: () =>
    request<RetailerBenchmarkCatalog>("/api/retailer-simulation/benchmarks"),

  retailerSimulationDefaults: () =>
    request<{ scenario: RetailerSimulationArtifact["scenario"] }>(
      "/api/retailer-simulation/defaults",
    ),

  retailerSimulationRun: (session: string, body: RetailerSimulationRunRequest) =>
    request<{ simulation: RetailerSimulationArtifact }>(
      `/api/sessions/${session}/retailer-simulation/run`,
      { method: "POST", body },
    ),

  retailerSimulationLast: (session: string) =>
    request<{ simulation: RetailerSimulationArtifact }>(
      `/api/sessions/${session}/retailer-simulation`,
    ),

  analogMatchingMeta: () =>
    request<AnalogMatchingMeta>("/api/analog-matching/meta"),

  analogMatchingSearch: (session: string, body: AnalogMatchingSearchRequest) =>
    request<{ search: AnalogSearchResult }>(
      `/api/sessions/${session}/analog-matching/search`,
      { method: "POST", body },
    ),

  analogMatchingLast: (session: string) =>
    request<{ search: AnalogSearchResult }>(
      `/api/sessions/${session}/analog-matching`,
    ),
};
