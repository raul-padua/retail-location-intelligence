"use client";

import clsx from "clsx";

import { percent, score } from "@/lib/format";
import { useSelection } from "@/lib/selection";
import { ProvenanceBadge } from "../ProvenanceBadge";

export function CandidateTray() {
  const { markers, selectedSlug, select } = useSelection();

  if (markers.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white/80 px-4 py-3 text-sm text-slate-500">
        Candidate regions will appear here once you select them in the plan.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Candidates
        </h2>
        <ProvenanceBadge badge={markers[0]?.geography.data_class} />
      </div>
      <ul className="flex gap-2 overflow-x-auto pb-1">
        {markers.map((marker) => {
          const selected = marker.geography.slug === selectedSlug;
          return (
            <li key={marker.geography.slug} className="shrink-0">
              <button
                type="button"
                onClick={() => select(marker.geography.slug)}
                className={clsx(
                  "min-w-[11rem] rounded-xl px-3 py-2.5 text-left transition",
                  selected
                    ? "bg-blue-600 text-white shadow-sm"
                    : "bg-white text-slate-800 ring-1 ring-slate-200 hover:bg-slate-50",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium leading-snug">
                    {marker.rank != null ? `${marker.rank}. ` : ""}
                    {marker.geography.display_name}
                  </p>
                  {marker.overall_score != null ? (
                    <span className="text-sm font-semibold tabular-nums">
                      {score(marker.overall_score)}
                    </span>
                  ) : null}
                </div>
                {marker.evidence_completeness != null ? (
                  <p
                    className={clsx(
                      "mt-1 text-[11px]",
                      selected ? "text-blue-100" : "text-slate-500",
                    )}
                  >
                    {percent(marker.evidence_completeness)} evidence
                  </p>
                ) : (
                  <p
                    className={clsx(
                      "mt-1 text-[11px]",
                      selected ? "text-blue-100" : "text-slate-500",
                    )}
                  >
                    {marker.geography.geography_type}
                  </p>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
