"use client";

/**
 * Step 5. The result, and every panel needed to interrogate it.
 *
 * Tab order is the map-first narrative: the answer, the comparison in market context,
 * reserved slots for later discovery/simulation/analog phases, then evidence, assumptions,
 * and the decision log. Secondary analytical panels (plan, sensitivity, versions) remain
 * available so nothing from the previous workspace was removed.
 */

import { useState } from "react";

import clsx from "clsx";

import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Badge, Banner, Button, EmptyState } from "../ui";
import { ArchetypesPanel } from "../panels/ArchetypesPanel";
import { AnalogsPanel } from "../panels/AnalogsPanel";
import { SimulationPanel } from "../panels/SimulationPanel";
import { AssumptionsPanel } from "../panels/AssumptionsPanel";
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
import { ProvenanceBadge } from "../ProvenanceBadge";

type TabId =
  | "recommendation"
  | "dashboard"
  | "archetypes"
  | "simulation"
  | "analogs"
  | "evidence"
  | "assumptions"
  | "trace"
  | "assistant"
  | "sensitivity"
  | "versions"
  | "plan"
  | "limitations"
  | "registry";

export function ExecutedStage({ compact }: { compact?: boolean }) {
  const { state, sessionId } = useSession();
  const [tab, setTab] = useState<TabId>("recommendation");
  const [exporting, setExporting] = useState(false);

  const current = state?.versions.at(-1);
  if (!current) {
    return <EmptyState>No analysis has been executed in this session.</EmptyState>;
  }

  const result = current.result;
  const refused = result.refused;
  const evidenceClass = result.evidence?.data_class;

  const tabs: { id: TabId; label: string; hidden?: boolean }[] = [
    { id: "recommendation", label: "Executive summary" },
    { id: "dashboard", label: "Market comparison", hidden: refused },
    { id: "archetypes", label: "Archetypes" },
    { id: "simulation", label: "Retailer simulation" },
    { id: "analogs", label: "Analog stores" },
    { id: "evidence", label: "Evidence" },
    { id: "assumptions", label: "Assumptions" },
    { id: "trace", label: "Decision log" },
    { id: "assistant", label: "Assistant" },
    { id: "sensitivity", label: "Sensitivity", hidden: refused },
    { id: "versions", label: "Versions", hidden: refused },
    { id: "plan", label: "Plan" },
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
    <div className={clsx("space-y-4", compact && "space-y-3")}>
      {state?.notice ? <Banner tone="accent">{state.notice}</Banner> : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={refused ? "warning" : "positive"}>
            {refused ? "Ranking withheld" : "Analysis complete"}
          </Badge>
          <Badge>Version {current.version}</Badge>
          <ProvenanceBadge badge={evidenceClass} />
          {state && state.versions.length > 1 ? (
            <Badge tone="accent">{state.versions.length} versions</Badge>
          ) : null}
        </div>
        <Button onClick={() => void exportResult()} disabled={exporting}>
          {exporting ? "Preparing…" : "Download full result as JSON"}
        </Button>
      </div>

      <nav
        className="flex flex-wrap gap-1 border-b border-slate-200"
        role="tablist"
        aria-label="Result views"
      >
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
                "-mb-px border-b-2 px-2.5 py-2 text-xs font-medium transition sm:text-sm",
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
        {tab === "dashboard" ? <DashboardPanel result={result} /> : null}
        {tab === "archetypes" ? <ArchetypesPanel /> : null}
        {tab === "simulation" ? <SimulationPanel /> : null}
        {tab === "analogs" ? <AnalogsPanel /> : null}
        {tab === "evidence" ? <EvidencePanel result={result} /> : null}
        {tab === "assumptions" ? <AssumptionsPanel result={result} /> : null}
        {tab === "trace" ? <TracePanel result={result} /> : null}
        {tab === "assistant" ? <AssistantPanel /> : null}
        {tab === "sensitivity" ? <SensitivityPanel /> : null}
        {tab === "versions" ? <VersionsPanel /> : null}
        {tab === "plan" ? <PlanView plan={current.plan} /> : null}
        {tab === "limitations" ? <LimitationsPanel result={result} /> : null}
        {tab === "registry" ? <RegistryPanel /> : null}
      </div>
    </div>
  );
}
