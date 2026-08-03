/**
 * Test harness.
 *
 * Components read the workflow through `useSession`, so the harness stubs `fetch` with a
 * routing table rather than mocking the context. That keeps the API client, the request
 * shapes, and the header handling inside the test boundary - the interesting bugs in a
 * client/server split live at the seam, not inside a component.
 */

import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { SessionProvider } from "@/lib/session";
import type { WorkflowState } from "@/lib/types";

import { catalogFixture, executedStateFixture } from "./fixtures.generated";

export interface StubOptions {
  state?: WorkflowState;
  llmEnabled?: boolean;
  atlasTokenPresent?: boolean;
  /** Extra routes, matched by substring against the request path. */
  routes?: Record<string, unknown>;
}

export interface Stub {
  calls: { url: string; method: string; headers: Record<string, string>; body: unknown }[];
  /** Requests that carried an OpenAI key header, for asserting on credential handling. */
  keyedCalls: () => Stub["calls"];
}

export function stubApi(options: StubOptions = {}): Stub {
  const state = options.state ?? executedStateFixture;
  const calls: Stub["calls"] = [];

  const routes: Record<string, unknown> = {
    "/api/health": {
      status: "ok",
      settings: {
        atlas_token_present: options.atlasTokenPresent ?? true,
        is_demo_token: true,
        atlas_base_url: "https://api.statebook.test",
        llm_enabled: options.llmEnabled ?? false,
        llm_model: "gpt-5.6-luna",
        llm_key_from_environment: false,
        default_llm_model: "gpt-5.6-luna",
      },
      demo_token_scope_note: catalogFixture.demo_token_scope_note,
    },
    "/api/catalog": catalogFixture,
    "/api/sessions": { session_id: "test-session", state },
    "/api/sessions/test-session/assistant": {
      messages: [],
      context: {
        suggestions: ["Why did the leading region come out on top?"],
        has_result: true,
        region_names: [],
        fact_count: 12,
      },
      llm_enabled: options.llmEnabled ?? false,
    },
    ...options.routes,
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({
        url,
        method: init?.method ?? "GET",
        headers: (init?.headers ?? {}) as Record<string, string>,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });

      // Prefer a suffix or exact path match over a bare prefix. Otherwise the create
      // route `/api/sessions` steals every `/api/sessions/{id}/…` call, and an `/edit`
      // stub never fires.
      const path = new URL(url, "http://local.test").pathname;
      const match =
        Object.keys(routes)
          .filter((route) => path === route || path.endsWith(route))
          .sort((a, b) => b.length - a.length)[0] ??
        Object.keys(routes)
          .filter((route) => path.includes(route))
          .sort((a, b) => b.length - a.length)[0];

      if (!match) {
        return new Response(JSON.stringify({ detail: `No stub for ${url}` }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(routes[match]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );

  return { calls, keyedCalls: () => calls.filter((call) => "X-OpenAI-Key" in call.headers) };
}

export function renderApp(ui: ReactElement): RenderResult {
  return render(<SessionProvider>{ui}</SessionProvider>);
}
