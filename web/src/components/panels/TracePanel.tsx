"use client";

/**
 * The agent decision log.
 *
 * The filter is the feature. A trace that lists forty steps in one undifferentiated column
 * answers "what happened" but not "who authorized this", and the second question is the
 * one a reviewer actually has. Filtering to human approval shows every point a person
 * signed off; filtering to agent inference shows every point the model was trusted, which
 * is the shortest possible audit of where the risk sits.
 */

import { useMemo, useState } from "react";

import { useSession } from "@/lib/session";
import type { AnalysisResult, TraceAuthority } from "@/lib/types";
import { Badge, Card, Cell, Disclosure, Json, Table } from "../ui";
import { AuthorityBadge } from "./AuthorityBadge";

export function TracePanel({ result }: { result: AnalysisResult }) {
  const { catalog } = useSession();
  const [selected, setSelected] = useState<Set<TraceAuthority>>(new Set());

  const authorities = useMemo(
    () =>
      Array.from(new Set(result.trace.map((entry) => entry.authority))) as TraceAuthority[],
    [result.trace],
  );

  const entries = selected.size
    ? result.trace.filter((entry) => selected.has(entry.authority))
    : result.trace;

  const toggle = (authority: TraceAuthority) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(authority)) next.delete(authority);
      else next.add(authority);
      return next;
    });

  return (
    <div className="space-y-6">
      <Card
        title="Decision log"
        description="Every step, and who or what is answerable for it."
      >
        <div className="mb-4 flex flex-wrap gap-2">
          {authorities.map((authority) => {
            const active = selected.has(authority);
            return (
              <button
                key={authority}
                type="button"
                onClick={() => toggle(authority)}
                aria-pressed={active}
                className={
                  active
                    ? "rounded-full ring-2 ring-blue-500 ring-offset-1"
                    : "rounded-full opacity-70 hover:opacity-100"
                }
              >
                <AuthorityBadge authority={authority} />
                <span className="sr-only">
                  {catalog?.authority_labels?.[authority] ?? authority}
                </span>
              </button>
            );
          })}
          {selected.size ? (
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="text-xs text-blue-700 hover:underline"
            >
              Clear filter
            </button>
          ) : null}
        </div>

        <ol className="space-y-3">
          {entries.map((entry, index) => (
            <li
              key={`${entry.step}-${index}`}
              className="rounded-lg border border-slate-200 px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-slate-400">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="text-sm font-medium text-slate-900">
                  {entry.step}
                </span>
                <AuthorityBadge authority={entry.authority} />
              </div>
              <p className="mt-1 text-sm text-slate-600">{entry.detail}</p>
              {entry.payload ? (
                <details className="mt-2">
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
      </Card>

      {result.weight_adjustments.length ? (
        <Card
          title="Weight renormalizations"
          description="A metric that could not be scored does not silently count as zero. Its weight is redistributed, and the adjustment is recorded here."
        >
          <Table columns={["Metric", "Category", "Original weight", "Reason"]} dense>
            {result.weight_adjustments.map((adjustment, index) => (
              <tr key={`${adjustment.metric_id}-${index}`}>
                <Cell className="font-medium">{adjustment.metric_id}</Cell>
                <Cell>{adjustment.category}</Cell>
                <Cell numeric>{adjustment.original_weight.toFixed(3)}</Cell>
                <Cell className="text-slate-600">{adjustment.reason}</Cell>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}

      <Disclosure summary="Final evidence package supplied to the explanation layer">
        <Json
          value={{
            package_id: result.evidence?.package_id,
            reproducibility_hash: result.reproducibility_hash,
            usable_values: result.evidence?.usable_count,
            total_values: result.evidence?.items.length,
            citations: result.recommendation?.citations ?? [],
          }}
        />
      </Disclosure>

      <div className="flex flex-wrap gap-2">
        {Object.entries(result.authority_counts).map(([authority, count]) => (
          <Badge key={authority}>
            {catalog?.authority_labels?.[authority as TraceAuthority] ?? authority}:{" "}
            {count}
          </Badge>
        ))}
      </div>
    </div>
  );
}
