"use client";

import { useSession } from "@/lib/session";
import { Disclosure, Json } from "../ui";
import { AuthorityBadge } from "./AuthorityBadge";

/** The planning-phase decision log, before any Atlas call exists to attribute. */
export function PlanningTrace() {
  const { state } = useSession();
  const entries = state?.planning_trace ?? [];
  if (!entries.length) return null;

  return (
    <Disclosure summary={`How this plan was produced (${entries.length} steps)`}>
      <ol className="space-y-3">
        {entries.map((entry, index) => (
          <li key={`${entry.step}-${index}`} className="text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-slate-500">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="font-medium text-slate-900">{entry.step}</span>
              <AuthorityBadge authority={entry.authority} />
            </div>
            <p className="mt-0.5 text-slate-600">{entry.detail}</p>
            {entry.payload ? (
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-blue-700">
                  payload
                </summary>
                <div className="mt-1">
                  <Json value={entry.payload} />
                </div>
              </details>
            ) : null}
          </li>
        ))}
      </ol>
    </Disclosure>
  );
}
