"use client";

import { useSession } from "@/lib/session";
import type { AnalysisResult } from "@/lib/types";
import { ProvenanceBadge } from "../ProvenanceBadge";
import { Banner, Card, EmptyState } from "../ui";

export function AssumptionsPanel({ result }: { result: AnalysisResult }) {
  const { state } = useSession();
  const plan = state?.versions.at(-1)?.plan ?? state?.plan;
  const assumptions = plan?.assumptions ?? [];
  const profileRows = plan?.profile_rows ?? [];
  const inferred = profileRows.filter((row) => row.provenance === "planner_inferred");

  return (
    <div className="space-y-4">
      <Banner tone="accent" title="Assumptions are not evidence">
        Values below shaped the plan or narrative. They are not Atlas measurements and must
        not be read as observed market facts.
      </Banner>

      <Card title="Plan assumptions">
        {assumptions.length ? (
          <ul className="space-y-2">
            {assumptions.map((assumption, index) => (
              <li
                key={`${assumption.subject}-${index}`}
                className="rounded-lg bg-amber-50 px-3 py-2 text-sm ring-1 ring-inset ring-amber-200"
              >
                <div className="mb-1">
                  <ProvenanceBadge
                    badge={{
                      data_class: "user_assumption",
                      label: "User assumption",
                      short_note: "Stated by the user; not measured.",
                    }}
                  />
                </div>
                <span className="font-medium text-amber-900">{assumption.subject}:</span>{" "}
                <span className="text-amber-900">{assumption.assumption}</span>
                <span className="mt-0.5 block text-xs text-amber-800">
                  {assumption.basis}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState>No explicit assumptions were recorded on this plan.</EmptyState>
        )}
      </Card>

      <Card title="Planner-inferred profile fields">
        {inferred.length ? (
          <ul className="space-y-2 text-sm text-slate-700">
            {inferred.map((row) => (
              <li key={row.name} className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-900">{row.label}</span>
                  <ProvenanceBadge
                    badge={{
                      data_class: "agent_interpretation",
                      label: "Agent interpretation",
                      short_note: "Planner or assistant wording. Not a data value.",
                    }}
                  />
                </div>
                <p>{row.value ?? "Not established"}</p>
                {row.note ? <p className="mt-1 text-xs text-slate-500">{row.note}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState>No planner-inferred profile fields on this plan.</EmptyState>
        )}
      </Card>

      {result.recommendation?.caveats.length ? (
        <Card title="Caveats attached to the recommendation">
          <ul className="space-y-1.5 text-sm text-slate-700">
            {result.recommendation.caveats.map((caveat) => (
              <li key={caveat}>• {caveat}</li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
