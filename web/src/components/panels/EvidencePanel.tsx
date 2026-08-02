"use client";

/**
 * Every value the analysis used, with the Atlas identifier, period, source, and the call
 * that produced it. This is what "traceable to an API response" has to mean in practice:
 * a reader can pick any number on the recommendation screen and land here.
 *
 * Raw request and response bodies are fetched on demand — they are ten times the size of
 * everything else and are only opened when someone is actually auditing a call.
 */

import { useState } from "react";

import { api } from "@/lib/api";
import { VALIDATION_LABELS, formatValue, percent, score } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AnalysisResult, RawCall } from "@/lib/types";
import { Badge, Card, Cell, Disclosure, EmptyState, Json, Table } from "../ui";

export function EvidencePanel({ result }: { result: AnalysisResult }) {
  const { sessionId } = useSession();
  const [loaded, setLoaded] = useState<{ packageId: string; calls: RawCall[] } | null>(
    null,
  );
  const [loadingCalls, setLoadingCalls] = useState(false);

  const evidence = result.evidence;

  // Tagging the cache with its package id means a new version invalidates it without an
  // effect that resets state on every render pass.
  const rawCalls =
    loaded && loaded.packageId === evidence?.package_id ? loaded.calls : null;

  if (!evidence) {
    return <EmptyState>No evidence package was produced for this run.</EmptyState>;
  }

  const items = [...evidence.items].sort((a, b) =>
    a.metric.metric_id === b.metric.metric_id
      ? a.geography.slug.localeCompare(b.geography.slug)
      : a.metric.metric_id.localeCompare(b.metric.metric_id),
  );

  const loadRawCalls = async () => {
    if (rawCalls || !sessionId) return;
    setLoadingCalls(true);
    try {
      const payload = await api.fullResult(sessionId, result.plan_version);
      setLoaded({
        packageId: evidence.package_id,
        calls: payload.result.evidence?.raw_calls ?? [],
      });
    } finally {
      setLoadingCalls(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card
        title="Evidence"
        description={`Package ${evidence.package_id} · ${evidence.usable_count} of ${evidence.items.length} values usable · ${percent(evidence.completeness)} complete`}
      >
        <Table
          columns={[
            "Metric",
            "Atlas datapoint",
            "Region",
            "Raw value",
            "Normalized",
            "Period",
            "Source",
            "Validation",
          ]}
          dense
        >
          {items.map((item) => (
            <tr key={item.evidence_id} className={item.is_usable ? undefined : "opacity-60"}>
              <Cell className="font-medium text-slate-900">
                {item.metric.display_name}
              </Cell>
              <Cell className="font-mono text-xs text-slate-600">
                {item.atlas_datapoint}
                {item.metric.atlas_item_code ? (
                  <span className="text-slate-400">
                    {" "}
                    [{item.metric.atlas_item_code}]
                  </span>
                ) : null}
              </Cell>
              <Cell>
                {item.geography.display_name}
                {item.geography_context_shifted && item.reported_geography ? (
                  <span
                    className="mt-0.5 block text-xs text-amber-700"
                    title="Atlas answered at a different level than requested"
                  >
                    answered for {item.reported_geography}
                  </span>
                ) : null}
              </Cell>
              <Cell numeric>{formatValue(item.raw_value, item.metric.unit)}</Cell>
              <Cell numeric>{score(item.normalized_value)}</Cell>
              <Cell className="text-xs">{item.period ?? "—"}</Cell>
              <Cell className="text-xs">{item.source ?? "—"}</Cell>
              <Cell>
                <Badge tone={item.is_usable ? "positive" : "warning"}>
                  {VALIDATION_LABELS[item.validation_status]}
                </Badge>
                {item.validation_notes.length ? (
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {item.validation_notes.join(" ")}
                  </span>
                ) : null}
              </Cell>
            </tr>
          ))}
        </Table>
      </Card>

      <Card
        title="Raw Atlas calls"
        description={`${evidence.raw_call_count} call(s). Bodies are fetched separately because they dominate the payload.`}
      >
        {rawCalls === null ? (
          <button
            type="button"
            onClick={() => void loadRawCalls()}
            disabled={loadingCalls}
            className="text-sm font-medium text-blue-700 hover:underline disabled:opacity-50"
          >
            {loadingCalls ? "Loading…" : "Load request and response bodies"}
          </button>
        ) : (
          <div className="space-y-2">
            {rawCalls.map((call) => (
              <Disclosure
                key={call.call_id}
                summary={
                  <span className="font-mono text-xs">
                    {call.method} {call.url} · {call.status_code} ·{" "}
                    {call.elapsed_seconds?.toFixed(3)}s · {call.attempts} attempt(s)
                  </span>
                }
              >
                <div className="grid gap-3 lg:grid-cols-2">
                  <div>
                    <p className="mb-1 text-xs font-medium text-slate-600">Request</p>
                    <Json value={call.request_body} />
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-medium text-slate-600">Response</p>
                    <Json value={call.response_body} />
                  </div>
                </div>
              </Disclosure>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
