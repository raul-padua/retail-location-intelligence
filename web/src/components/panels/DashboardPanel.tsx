"use client";

/**
 * The comparison dashboard: overall scores, category breakdown, and the metric table the
 * scores were computed from.
 *
 * The metric table shows raw Atlas values rather than normalized ones. Normalized values
 * are what the scorer uses, but "97.8%" means something to a reader and "83.4 out of 100
 * after min-max across three candidates" does not.
 */

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

import { categoryColor, formatValue, percent, score } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AnalysisResult } from "@/lib/types";
import { Badge, Card, Cell, EmptyState, SectionHeading, Table } from "../ui";

export function DashboardPanel({ result }: { result: AnalysisResult }) {
  const { catalog } = useSession();
  const ranked = result.recommendation?.ranked_regions ?? [];
  const evidence = result.evidence;

  if (!ranked.length || !evidence) {
    return <EmptyState>No scored comparison is available for this run.</EmptyState>;
  }

  const chartData = ranked.map((region) => ({
    name: region.geography.display_name,
    score: region.overall_score ?? 0,
    rank: region.rank,
  }));

  const categories = catalog?.categories ?? [];
  const excluded = new Set(
    evidence.excluded_metrics.map((entry) => entry.metric_id),
  );

  const metricIds = Array.from(
    new Set(evidence.items.map((item) => item.metric.metric_id)),
  );

  return (
    <div className="space-y-6">
      <Card
        title="Overall score by region"
        description="A relative comparison of these candidates only. A score of 100 means best of this set, not best possible."
      >
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 8, right: 24, top: 8, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" domain={[0, 100]} fontSize={12} />
              <YAxis
                type="category"
                dataKey="name"
                width={150}
                fontSize={12}
                tickLine={false}
              />
              <Tooltip
                formatter={(value) => [score(Number(value)), "Score"]}
                cursor={{ fill: "rgba(148, 163, 184, 0.12)" }}
              />
              <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                {chartData.map((entry) => (
                  <ChartCell
                    key={entry.name}
                    fill={entry.rank === 1 ? "#2563eb" : "#93c5fd"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card
        title="Category scores"
        description="Where each region's overall score came from. Empty means no usable metric survived validation for that category."
      >
        <Table
          columns={[
            "Category",
            "What it measures",
            ...ranked.map((region) => region.geography.display_name),
          ]}
          dense
        >
          {categories.map((category) => {
            const cells = ranked.map((region) =>
              region.category_scores.find(
                (entry) => entry.category === category.id,
              ),
            );
            if (cells.every((entry) => !entry)) return null;
            return (
              <tr key={category.id}>
                <Cell className="font-medium text-slate-900">
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: categoryColor(category.id) }}
                    />
                    {category.label}
                  </span>
                </Cell>
                <Cell className="max-w-xs text-xs text-slate-500">
                  {category.description}
                </Cell>
                {cells.map((entry, index) => (
                  <Cell key={index} numeric>
                    {entry?.score == null ? (
                      <span className="text-slate-400">—</span>
                    ) : (
                      <>
                        <span className="font-medium">{score(entry.score)}</span>
                        <span className="ml-1 text-xs text-slate-400">
                          {entry.metrics_included}/{entry.metrics_total}
                        </span>
                      </>
                    )}
                  </Cell>
                ))}
              </tr>
            );
          })}
        </Table>
      </Card>

      <Card
        title="Metric-level comparison"
        description="Raw Atlas values as returned. Excluded metrics are shown so their absence is visible rather than inferred from a gap."
      >
        <Table
          columns={[
            "Metric",
            "Unit",
            ...ranked.map((region) => region.geography.display_name),
            "Status",
          ]}
          dense
        >
          {metricIds.map((metricId) => {
            const items = evidence.items.filter(
              (item) => item.metric.metric_id === metricId,
            );
            const metric = items[0]?.metric;
            if (!metric) return null;
            const isExcluded = excluded.has(metricId);
            return (
              <tr key={metricId} className={isExcluded ? "opacity-60" : undefined}>
                <Cell>
                  <span className="font-medium text-slate-900">
                    {metric.display_name}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {metric.category_label}
                  </span>
                </Cell>
                <Cell className="text-xs text-slate-500">{metric.unit}</Cell>
                {ranked.map((region) => {
                  const item = items.find(
                    (entry) => entry.geography.slug === region.geography.slug,
                  );
                  return (
                    <Cell key={region.geography.slug} numeric>
                      {item && item.is_usable ? (
                        formatValue(item.raw_value, metric.unit)
                      ) : (
                        <span className="text-slate-400">n/a</span>
                      )}
                    </Cell>
                  );
                })}
                <Cell>
                  {isExcluded ? (
                    <Badge tone="warning">Excluded</Badge>
                  ) : (
                    <Badge tone="positive">Scored</Badge>
                  )}
                </Cell>
              </tr>
            );
          })}
        </Table>
      </Card>

      {evidence.excluded_metrics.length ? (
        <Card title="Why metrics were excluded">
          <SectionHeading hint="Excluding a metric redistributes its weight. The adjustment is in the decision log.">
            {evidence.excluded_metrics.length} metric(s) did not survive validation
          </SectionHeading>
          <Table columns={["Metric", "Status", "Reason"]} dense>
            {evidence.excluded_metrics.map((entry) => (
              <tr key={entry.metric_id}>
                <Cell className="font-medium">{entry.display_name}</Cell>
                <Cell>{entry.status}</Cell>
                <Cell className="text-slate-600">{entry.reason}</Cell>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}

      <p className="text-xs text-slate-500">
        Evidence completeness across the package: {percent(evidence.completeness)} (
        {evidence.usable_count} of {evidence.items.length} metric-region pairs usable).
      </p>
    </div>
  );
}
