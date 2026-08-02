"use client";

/**
 * Stage router. The server's `stage` is the only thing that decides what renders, which is
 * why there is no local notion of "which screen am I on" to fall out of sync with it.
 */

import { useSession } from "@/lib/session";
import { Banner, Button } from "./ui";
import { Sidebar } from "./Sidebar";
import { ClarifyStage } from "./stages/ClarifyStage";
import { DescribeStage } from "./stages/DescribeStage";
import { ExecutedStage } from "./stages/ExecutedStage";
import { RefusedStage } from "./stages/RefusedStage";
import { ReviewStage } from "./stages/ReviewStage";

export function Workspace() {
  const { state, booting, bootError, error, dismissError, settings } = useSession();

  if (bootError) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <Banner tone="negative" title="Cannot reach the analysis service">
          <p className="mt-1">{bootError}</p>
          <p className="mt-3 text-xs">
            Start it from the project root with{" "}
            <code className="rounded bg-white/60 px-1 py-0.5 font-mono">
              uv run uvicorn server.app:app --port 8000
            </code>
            .
          </p>
        </Banner>
      </main>
    );
  }

  if (booting || !state) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-500">Connecting to the analysis service…</p>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <Sidebar />
      <main className="min-w-0 flex-1 px-5 py-6 lg:px-8 lg:py-8">
        <div className="mx-auto max-w-6xl space-y-5">
          {!settings?.atlas_token_present ? (
            <Banner tone="negative" title="No Atlas token is configured">
              Copy <code className="font-mono">.env.example</code> to{" "}
              <code className="font-mono">.env</code> and set{" "}
              <code className="font-mono">STATEBOOK_API_TOKEN=demo</code> to use the public
              evaluation token. Planning works without it; running an analysis does not.
            </Banner>
          ) : null}

          {error ? (
            <Banner tone="negative">
              <div className="flex items-start justify-between gap-4">
                <span>{error}</span>
                <Button variant="ghost" onClick={dismissError} className="shrink-0 py-0">
                  Dismiss
                </Button>
              </div>
            </Banner>
          ) : null}

          {state.notice && state.stage !== "executed" ? (
            <Banner tone="accent">{state.notice}</Banner>
          ) : null}

          {state.stage === "describe" ? <DescribeStage /> : null}
          {state.stage === "clarify" ? <ClarifyStage /> : null}
          {state.stage === "review" ? <ReviewStage /> : null}
          {state.stage === "refused" ? <RefusedStage /> : null}
          {state.stage === "executed" ? <ExecutedStage /> : null}
        </div>
      </main>
    </div>
  );
}
