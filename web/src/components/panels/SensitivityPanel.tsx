"use client";

/**
 * Strategy lenses, metric influence, and flip points.
 *
 * Everything here is deterministic re-scoring of evidence already in hand: no Atlas call,
 * no model. The framing matters as much as the numbers — a lens is a decision posture, not
 * a competing claim about which region is objectively best, and the panel says so rather
 * than presenting four rankings and leaving the reader to guess which one is true.
 */

import { useEffect, useState } from "react";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell as ChartCell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiError, api } from "@/lib/api";
import { categoryColor, percent, score, signed, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { SensitivityReport } from "@/lib/types";
import {
  Badge,
  Banner,
  Card,
  Cell,
  Disclosure,
  EmptyState,
  Field,
  Table,
} from "../ui";

export function SensitivityPanel() {
  const { sessionId, state, catalog } = useSession();
  const [loaded, setLoaded] = useState<{
    packageId: string;
    report: SensitivityReport;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [regionChoice, setRegionChoice] = useState<string | null>(null);

  const packageId = state?.versions.at(-1)?.result.evidence?.package_id;

  // The report is keyed by evidence package, so a confirmed revision invalidates it
  // without any state reset: a stale package id simply reads as "not loaded".
  const report = loaded && loaded.packageId === packageId ? loaded.report : null;

  useEffect(() => {
    if (!sessionId || !packageId) return;
    let cancelled = false;
    (async () => {
      try {
        const fetched = await api.sensitivity(sessionId);
        if (cancelled) return;
        setLoaded({ packageId, report: fetched });
        setError(null);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : String(caught));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, packageId]);

  if (error) return <Banner tone="negative">{error}</Banner>;
  if (!report) return <EmptyState>Computing strategy lenses…</EmptyState>;

  const region =
    regionChoice ?? report.comparison.baseline.regions[0]?.slug ?? "";

  const rankings = [report.comparison.baseline, ...report.comparison.profiles];
  const influences = report.influences.filter((entry) => entry.slug === region);
  const influenceData = influences
    .slice()
    .sort((a, b) => b.contribution - a.contribution)
    .map((entry) => ({
      name: entry.metric_name,
      contribution: Number(entry.contribution.toFixed(2)),
      category: entry.category,
      share: entry.share_of_score,
    }));

  return (
    <div className="space-y-6">
      <Banner tone={report.comparison.stable ? "positive" : "warning"}>
        {report.comparison.stability_note}
      </Banner>

      <Card
        title="Ranking under each lens"
        description="The same evidence, weighted by a different strategic posture. Each lens has its own reproducibility hash, so none of these is a relabelling of another."
      >
        <Table
          columns={[
            "Lens",
            ...report.comparison.baseline.regions.map((r) => r.display_name),
            "Hash",
          ]}
          dense
        >
          {rankings.map((ranking) => (
            <tr key={ranking.profile_id}>
              <Cell className="font-medium text-slate-900">
                {ranking.display_name}
                {ranking.profile_id === report.comparison.baseline.profile_id ? (
                  <Badge className="ml-2" tone="accent">
                    Your plan
                  </Badge>
                ) : null}
              </Cell>
              {report.comparison.baseline.regions.map((baselineRegion) => {
                const entry = ranking.regions.find(
                  (candidate) => candidate.slug === baselineRegion.slug,
                );
                return (
                  <Cell key={baselineRegion.slug} numeric>
                    {entry ? (
                      <>
                        <span
                          className={
                            entry.rank === 1
                              ? "font-semibold text-blue-700"
                              : "text-slate-700"
                          }
                        >
                          #{entry.rank}
                        </span>
                        <span className="ml-1.5 text-xs text-slate-400">
                          {score(entry.overall_score)}
                        </span>
                      </>
                    ) : (
                      "—"
                    )}
                  </Cell>
                );
              })}
              <Cell className="font-mono text-xs text-slate-500">
                {ranking.reproducibility_hash.slice(0, 12)}
              </Cell>
            </tr>
          ))}
        </Table>

        <Disclosure
          summary="What each lens weights, and when you would use it"
          defaultOpen={false}
        >
          <div className="space-y-3">
            {catalog?.strategy_profiles.map((profile) => (
              <div key={profile.profile_id}>
                <p className="text-sm font-medium text-slate-900">
                  {profile.display_name}
                </p>
                <p className="text-sm text-slate-600">{profile.description}</p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {profile.when_to_use}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {Object.entries(profile.category_weights)
                    .map(
                      ([category, weight]) =>
                        `${titleCase(category)} ${percent(weight, 0)}`,
                    )
                    .join(" · ")}
                </p>
              </div>
            ))}
          </div>
        </Disclosure>
      </Card>

      <Card
        title="What moved between lenses"
        description="Rank and score changes against your approved weighting."
      >
        {Object.entries(report.comparison.deltas).map(([profileId, deltas]) => (
          <div key={profileId} className="mb-4 last:mb-0">
            <p className="mb-1.5 text-sm font-medium text-slate-900">
              {titleCase(profileId)}
            </p>
            <Table
              columns={["Region", "Rank", "Change", "Score", "Change"]}
              dense
            >
              {deltas.map((delta) => (
                <tr key={delta.slug}>
                  <Cell>{delta.display_name}</Cell>
                  <Cell numeric>
                    {delta.baseline_rank} → {delta.comparison_rank}
                  </Cell>
                  <Cell numeric>
                    {delta.rank_change === 0 ? (
                      <span className="text-slate-400">held</span>
                    ) : (
                      <span
                        className={
                          delta.rank_change > 0
                            ? "text-emerald-700"
                            : "text-rose-700"
                        }
                      >
                        {delta.rank_change > 0 ? "▲" : "▼"}{" "}
                        {Math.abs(delta.rank_change)}
                      </span>
                    )}
                  </Cell>
                  <Cell numeric>{score(delta.comparison_score)}</Cell>
                  <Cell numeric>{signed(delta.score_change)}</Cell>
                </tr>
              ))}
            </Table>
          </div>
        ))}
      </Card>

      <Card
        title="Which metrics drove each score"
        description="Points of the 0–100 score contributed by each metric, under your approved weights."
      >
        <Field label="Region" htmlFor="influence-region">
          <select
            id="influence-region"
            value={region}
            onChange={(event) => setRegionChoice(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {report.comparison.baseline.regions.map((entry) => (
              <option key={entry.slug} value={entry.slug}>
                {entry.display_name}
              </option>
            ))}
          </select>
        </Field>

        <div className="mt-4 h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={influenceData}
              layout="vertical"
              margin={{ left: 8, right: 24, top: 8, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" fontSize={12} />
              <YAxis
                type="category"
                dataKey="name"
                width={190}
                fontSize={11}
                tickLine={false}
              />
              <Tooltip
                formatter={(value) => [`${Number(value)} pts`, "Contribution"]}
                cursor={{ fill: "rgba(148, 163, 184, 0.12)" }}
              />
              <Bar dataKey="contribution" radius={[0, 4, 4, 0]}>
                {influenceData.map((entry) => (
                  <ChartCell
                    key={entry.name}
                    fill={categoryColor(entry.category)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card
        title="What would have to change to flip the top two"
        description="A deterministic scan of one category weight at a time. Interaction effects between two simultaneous changes are not explored."
      >
        <Table
          columns={["Category", "Current weight", "Flips?", "Required weight", "Note"]}
          dense
        >
          {report.flip_points.map((point) => (
            <tr key={point.category}>
              <Cell className="font-medium">{titleCase(point.category)}</Cell>
              <Cell numeric>{percent(point.current_weight, 0)}</Cell>
              <Cell>
                {point.flips ? (
                  <Badge tone="warning">Yes</Badge>
                ) : (
                  <Badge tone="positive">No</Badge>
                )}
              </Cell>
              <Cell numeric>
                {point.required_weight == null
                  ? "—"
                  : percent(point.required_weight, 0)}
              </Cell>
              <Cell className="text-slate-600">{point.note}</Cell>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}
