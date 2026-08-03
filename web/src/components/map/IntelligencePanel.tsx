"use client";

import type { ReactNode } from "react";

import { percent, score } from "@/lib/format";
import { useSelection } from "@/lib/selection";
import { useSession } from "@/lib/session";
import { ProvenanceBadge } from "../ProvenanceBadge";
import { Banner, EmptyState } from "../ui";

export function IntelligencePanel({ children }: { children: ReactNode }) {
  const { selected, markers } = useSelection();
  const { state } = useSession();
  const executed = state?.stage === "executed";

  return (
    <aside className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col border-slate-200 bg-white lg:border-l">
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Intelligence panel
        </p>
        {selected ? (
          <div className="mt-2 space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {selected.geography.display_name}
                </h2>
                <p className="text-xs text-slate-500">{selected.geography.slug}</p>
              </div>
              <ProvenanceBadge badge={selected.geography.data_class} />
            </div>
            {executed && selected.overall_score != null ? (
              <dl className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                    Rank
                  </dt>
                  <dd className="font-semibold tabular-nums text-slate-900">
                    {selected.rank ?? "—"}
                  </dd>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                    Score
                  </dt>
                  <dd className="font-semibold tabular-nums text-slate-900">
                    {score(selected.overall_score)}
                  </dd>
                </div>
                <div className="col-span-2 rounded-lg bg-slate-50 px-3 py-2">
                  <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                    Evidence completeness
                  </dt>
                  <dd className="font-semibold tabular-nums text-slate-900">
                    {percent(selected.evidence_completeness ?? null)}
                  </dd>
                </div>
              </dl>
            ) : null}
            {!executed ? (
              <p className="text-xs leading-relaxed text-slate-500">
                Nothing has run for this market yet. Approve a plan to retrieve Atlas
                evidence and score candidates.
              </p>
            ) : null}
          </div>
        ) : (
          <EmptyState>
            {markers.length
              ? "Select a market on the map or in the tray."
              : "Select candidate regions to populate the map."}
          </EmptyState>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">{children}</div>
    </aside>
  );
}

export function ComingSoonPanel({
  title,
  phase,
}: {
  title: string;
  phase: string;
}) {
  return (
    <Banner tone="accent" title={`${title} — ${phase}`}>
      This view is reserved for a later phase. The map and Atlas comparison workflow remain
      fully available; nothing here invents market or retailer data.
    </Banner>
  );
}
