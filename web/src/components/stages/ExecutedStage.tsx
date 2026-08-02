"use client";

/**
 * Step 5. The result, and every panel needed to interrogate it.
 *
 * Tab order is the order a sceptical reader works through: the answer, then a way to argue
 * with it, then how sensitive it is, then what changed, then the underlying values, the
 * plan that authorized them, the log of who did what, and finally what the whole thing
 * could not do.
 */

import { useState } from "react";

import clsx from "clsx";

import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Badge, Banner, Button, EmptyState } from "../ui";
import { AssistantPanel } from "../panels/AssistantPanel";
import { DashboardPanel } from "../panels/DashboardPanel";
import { EvidencePanel } from "../panels/EvidencePanel";
import { LimitationsPanel } from "../panels/LimitationsPanel";
import { PlanView } from "../panels/PlanView";
import { RecommendationPanel } from "../panels/RecommendationPanel";
import { RegistryPanel } from "../panels/RegistryPanel";
import { SensitivityPanel } from "../panels/SensitivityPanel";
import { TracePanel } from "../panels/TracePanel";
import { VersionsPanel } from "../panels/VersionsPanel";

type TabId =
  | "recommendation"
  | "assistant"
  | "dashboard"
  | "sensitivity"
  | "versions"
  | "evidence"
  | "plan"
  | "trace"
  | "limitations"
  | "registry";

export function ExecutedStage() {
  const { state, sessionId } = useSession();
  const [tab, setTab] = useState<TabId>("recommendation");
  const [exporting, setExporting] = useState(false);

  const current = state?.versions.at(-1);
  if (!current) {
    return <EmptyState>No analysis has been executed in this session.</EmptyState>;
  }

  const result = current.result;
  const refused = result.refused;

  const tabs: { id: TabId; label: string; hidden?: boolean }[] = [
    { id: "recommendation", label: "Recommendation" },
    { id: "assistant", label: "Assistant" },
    { id: "dashboard", label: "Comparison", hidden: refused },
    { id: "sensitivity", label: "Sensitivity", hidden: refused },
    { id: "versions", label: "Versions", hidden: refused },
    { id: "evidence", label: "Evidence" },
    { id: "plan", label: "Plan" },
    { id: "trace", label: "Decision log" },
    { id: "limitations", label: "Limitations" },
    { id: "registry", label: "Registry" },
  ];

  const exportResult = async () => {
    if (!sessionId) return;
    setExporting(true);
    try {
      const payload = await api.fullResult(sessionId, current.version);
      const blob = new Blob([JSON.stringify(payload.result, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `retail-location-analysis-v${current.version}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-5">
      {state?.notice ? <Banner tone="accent">{state.notice}</Banner> : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={refused ? "warning" : "positive"}>
            {refused ? "Ranking withheld" : "Analysis complete"}
          </Badge>
          <Badge>Version {current.version}</Badge>
          {state && state.versions.length > 1 ? (
            <Badge tone="accent">{state.versions.length} versions</Badge>
          ) : null}
        </div>
        <Button onClick={() => void exportResult()} disabled={exporting}>
          {exporting ? "Preparing…" : "Download full result as JSON"}
        </Button>
      </div>

      <nav className="flex flex-wrap gap-1 border-b border-slate-200" role="tablist">
        {tabs
          .filter((entry) => !entry.hidden)
          .map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="tab"
              aria-selected={tab === entry.id}
              onClick={() => setTab(entry.id)}
              className={clsx(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition",
                tab === entry.id
                  ? "border-blue-600 text-blue-700"
                  : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700",
              )}
            >
              {entry.label}
            </button>
          ))}
      </nav>

      <div role="tabpanel">
        {tab === "recommendation" ? <RecommendationPanel result={result} /> : null}
        {tab === "assistant" ? <AssistantPanel /> : null}
        {tab === "dashboard" ? <DashboardPanel result={result} /> : null}
        {tab === "sensitivity" ? <SensitivityPanel /> : null}
        {tab === "versions" ? <VersionsPanel /> : null}
        {tab === "evidence" ? <EvidencePanel result={result} /> : null}
        {tab === "plan" ? <PlanView plan={current.plan} /> : null}
        {tab === "trace" ? <TracePanel result={result} /> : null}
        {tab === "limitations" ? <LimitationsPanel result={result} /> : null}
        {tab === "registry" ? <RegistryPanel /> : null}
      </div>
    </div>
  );
}
