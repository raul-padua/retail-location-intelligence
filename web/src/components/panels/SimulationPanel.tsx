"use client";

/**
 * NorthStar Apparel fictional retailer simulation (Phase 3).
 *
 * All numbers are server-generated simulated data. Scenario inputs are explicit POST
 * parameters — never silently mutated by the agent.
 */

import { useEffect, useMemo, useState } from "react";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell as ChartCell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, ApiError } from "@/lib/api";
import { useSelection } from "@/lib/selection";
import { useSession } from "@/lib/session";
import type {
  RetailerBenchmarkCatalog,
  RetailerSimulationArtifact,
  RetailerSimulationMeta,
} from "@/lib/types";
import { ProvenanceBadge } from "../ProvenanceBadge";
import {
  Badge,
  Banner,
  Button,
  Card,
  Disclosure,
  EmptyState,
  Field,
  SectionHeading,
  Table,
  Cell,
} from "../ui";

const SEGMENT_COLORS = ["#2563eb", "#7c3aed", "#059669", "#d97706"];

function formatUsd(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${Math.round(value).toLocaleString("en-US")}`;
  return `$${value.toFixed(0)}`;
}

export function SimulationPanel() {
  const { sessionId } = useSession();
  const { selectedSlug, selected } = useSelection();
  const [meta, setMeta] = useState<RetailerSimulationMeta | null>(null);
  const [benchmarks, setBenchmarks] = useState<RetailerBenchmarkCatalog | null>(null);
  const [simulation, setSimulation] = useState<RetailerSimulationArtifact | null>(null);
  const [storeCount, setStoreCount] = useState(48);
  const [seed, setSeed] = useState(42);
  const [salesTarget, setSalesTarget] = useState(200_000_000);
  const [marginMin, setMarginMin] = useState(34);
  const [marginMax, setMarginMax] = useState(42);
  const [mallMix, setMallMix] = useState(35);
  const [stripMix, setStripMix] = useState(40);
  const [outletMix, setOutletMix] = useState(25);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [metaPayload, benchmarkPayload, defaultsPayload] = await Promise.all([
          api.retailerSimulationMeta(),
          api.retailerSimulationBenchmarks(),
          api.retailerSimulationDefaults(),
        ]);
        if (cancelled) return;
        setMeta(metaPayload);
        setBenchmarks(benchmarkPayload);
        const scenario = defaultsPayload.scenario;
        setStoreCount(scenario.store_count);
        setSeed(scenario.seed);
        setSalesTarget(scenario.sales_target_usd);
        setMarginMin(scenario.margin_min_pct);
        setMarginMax(scenario.margin_max_pct);
        setMallMix(Math.round((scenario.format_mix.mall ?? 0.35) * 100));
        setStripMix(Math.round((scenario.format_mix.strip ?? 0.4) * 100));
        setOutletMix(Math.round((scenario.format_mix.outlet ?? 0.25) * 100));

        if (sessionId) {
          try {
            const last = await api.retailerSimulationLast(sessionId);
            if (!cancelled) setSimulation(last.simulation);
          } catch (err) {
            // No prior run, or the serverless instance no longer holds this session.
            if (
              !(
                err instanceof ApiError &&
                (err.status === 404 || err.isMissingSession)
              )
            ) {
              throw err;
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Failed to load simulation metadata.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const runSimulation = async () => {
    setRunning(true);
    setError(null);
    try {
      const mixTotal = mallMix + stripMix + outletMix;
      // Stateless run — does not depend on in-memory workflow sessions (important on Vercel).
      const payload = await api.retailerSimulationRun({
        store_count: storeCount,
        seed,
        sales_target_usd: salesTarget,
        margin_min_pct: marginMin,
        margin_max_pct: marginMax,
        focus_market_id: selectedSlug,
        format_mix: {
          mall: mallMix / mixTotal,
          strip: stripMix / mixTotal,
          outlet: outletMix / mixTotal,
        },
      });
      setSimulation(payload.simulation);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Simulation run failed.");
    } finally {
      setRunning(false);
    }
  };

  const monthlyChart = useMemo(
    () =>
      (simulation?.monthly ?? []).map((entry) => ({
        name: entry.label,
        sales: entry.total_sales_usd,
      })),
    [simulation],
  );

  const segmentChart = useMemo(
    () =>
      (simulation?.segments ?? []).map((entry, index) => ({
        name: entry.label,
        value: entry.share_pct,
        fill: SEGMENT_COLORS[index % SEGMENT_COLORS.length],
      })),
    [simulation],
  );

  if (loading) {
    return <EmptyState>Loading NorthStar Apparel simulation…</EmptyState>;
  }

  return (
    <div className="space-y-6">
      <Banner tone="warning" title="Simulated retailer data">
        NorthStar Apparel is a fictional brand. Outputs are equation-based and seeded — not
        observed GAP or any real retailer store performance.
      </Banner>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <SectionHeading>Retailer simulation</SectionHeading>
          <p className="mt-1 max-w-xl text-sm text-slate-600">
            Build a fictional NorthStar Apparel network for demos. When a candidate is
            selected on the map, the run also profiles simulated store performance in
            markets that share that area’s public-market archetype.
          </p>
        </div>
        <ProvenanceBadge badge={simulation?.data_class ?? meta?.data_class} showNote />
      </div>

      {meta ? (
        <p className="text-xs text-slate-500">
          {meta.brand} · simulator {meta.simulator_version} · benchmark {meta.benchmark_version}
        </p>
      ) : null}

      {error ? (
        <Banner tone="negative" title="Simulation error">
          {error}
        </Banner>
      ) : null}

      <Card title="Scenario inputs (user assumptions)">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Store count" htmlFor="sim-store-count">
            <input
              id="sim-store-count"
              type="number"
              min={1}
              max={500}
              value={storeCount}
              onChange={(event) => setStoreCount(Number(event.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Seed" htmlFor="sim-seed">
            <input
              id="sim-seed"
              type="number"
              value={seed}
              onChange={(event) => setSeed(Number(event.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Annual sales target (USD)" htmlFor="sim-sales-target">
            <input
              id="sim-sales-target"
              type="number"
              min={1}
              value={salesTarget}
              onChange={(event) => setSalesTarget(Number(event.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Margin min (%)" htmlFor="sim-margin-min">
            <input
              id="sim-margin-min"
              type="number"
              min={0}
              max={100}
              value={marginMin}
              onChange={(event) => setMarginMin(Number(event.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Margin max (%)" htmlFor="sim-margin-max">
            <input
              id="sim-margin-max"
              type="number"
              min={0}
              max={100}
              value={marginMax}
              onChange={(event) => setMarginMax(Number(event.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Format mix (mall / strip / outlet %)" htmlFor="sim-mall-mix">
            <div className="flex gap-2">
              <input
                id="sim-mall-mix"
                type="number"
                min={0}
                value={mallMix}
                onChange={(event) => setMallMix(Number(event.target.value))}
                className="w-full rounded-md border border-slate-300 px-2 py-2 text-sm"
                aria-label="Mall mix percent"
              />
              <input
                type="number"
                min={0}
                value={stripMix}
                onChange={(event) => setStripMix(Number(event.target.value))}
                className="w-full rounded-md border border-slate-300 px-2 py-2 text-sm"
                aria-label="Strip mix percent"
              />
              <input
                type="number"
                min={0}
                value={outletMix}
                onChange={(event) => setOutletMix(Number(event.target.value))}
                className="w-full rounded-md border border-slate-300 px-2 py-2 text-sm"
                aria-label="Outlet mix percent"
              />
            </div>
          </Field>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {selectedSlug
            ? `Similar-market profile will focus on: ${selected?.geography.display_name ?? selectedSlug}`
            : "Select a candidate on the map to focus the similar-market store profile."}
        </p>
        <div className="mt-4">
          <Button onClick={() => void runSimulation()} disabled={running}>
            {running ? "Running…" : "Run simulation"}
          </Button>
        </div>
      </Card>

      {benchmarks ? (
        <Disclosure summary="Public benchmark sources">
          <ul className="mt-2 space-y-2 text-sm text-slate-600">
            {benchmarks.benchmarks.map((entry) => (
              <li key={entry.metric} className="flex flex-wrap items-center gap-2">
                <Badge tone={entry.verification_state === "UNVERIFIED_DISABLED" ? "neutral" : "accent"}>
                  {entry.verification_state}
                </Badge>
                <span className="font-medium text-slate-800">{entry.metric}</span>
                <span>
                  {entry.value.toLocaleString("en-US")} {entry.unit}
                </span>
                <span className="text-xs text-slate-500">— {entry.usage}</span>
              </li>
            ))}
          </ul>
        </Disclosure>
      ) : null}

      {simulation ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={simulation.reconciliation_passed ? "positive" : "warning"}>
              Reconciliation {simulation.reconciliation_passed ? "passed" : "failed"}
            </Badge>
            <Badge>Seed {simulation.seed}</Badge>
            <Badge>{simulation.simulator_version}</Badge>
            <Badge>{simulation.stores.length} stores</Badge>
          </div>

          <Disclosure summary="Assumptions">
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {simulation.assumptions.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </Disclosure>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Monthly sales distribution">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={monthlyChart}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tickFormatter={(value) => formatUsd(Number(value))} width={70} />
                    <Tooltip
                      formatter={(value) =>
                        formatUsd(typeof value === "number" ? value : Number(value))
                      }
                    />
                    <Bar dataKey="sales" fill="#2563eb" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card title="Customer segments">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={segmentChart} dataKey="value" nameKey="name" label>
                      {segmentChart.map((entry) => (
                        <ChartCell key={entry.name} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value) =>
                        `${typeof value === "number" ? value.toFixed(1) : String(value)}%`
                      }
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card title="Reconciliation">
            <Table
              dense
              columns={["Metric", "Target", "Generated", "Tolerance", "Pass", "Note"]}
            >
              {simulation.reconciliation.map((line) => (
                <tr key={line.metric} className="border-b border-slate-100">
                  <Cell>{line.metric}</Cell>
                  <Cell>{line.target.toLocaleString("en-US")}</Cell>
                  <Cell>{line.generated.toLocaleString("en-US")}</Cell>
                  <Cell>{(line.tolerance_pct * 100).toFixed(1)}%</Cell>
                  <Cell>{line.passed ? "Yes" : "No"}</Cell>
                  <Cell>{line.note}</Cell>
                </tr>
              ))}
            </Table>
          </Card>

          {simulation.similar_market_profile ? (
            <Card
              title="Performance in similar markets"
              description="Fictional NorthStar stores hosted in counties that share the selected area’s public-market archetype. Demo context only — not a forecast."
              actions={
                <ProvenanceBadge badge={simulation.similar_market_profile.data_class} />
              }
            >
              <p className="mb-3 text-sm text-slate-600">
                {simulation.similar_market_profile.note}
              </p>
              {simulation.similar_market_profile.store_count > 0 ? (
                <dl className="mb-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg bg-slate-50 px-3 py-2">
                    <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                      Peer stores
                    </dt>
                    <dd className="font-semibold tabular-nums text-slate-900">
                      {simulation.similar_market_profile.store_count}
                      {simulation.similar_market_profile.cluster_id
                        ? ` · ${simulation.similar_market_profile.cluster_id}`
                        : ""}
                    </dd>
                  </div>
                  <div className="rounded-lg bg-slate-50 px-3 py-2">
                    <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                      Median simulated sales
                    </dt>
                    <dd className="font-semibold tabular-nums text-slate-900">
                      {formatUsd(
                        simulation.similar_market_profile.median_annual_sales_usd ?? 0,
                      )}
                    </dd>
                  </div>
                  <div className="rounded-lg bg-slate-50 px-3 py-2">
                    <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                      Median margin
                    </dt>
                    <dd className="font-semibold tabular-nums text-slate-900">
                      {(
                        simulation.similar_market_profile.median_gross_margin_pct ?? 0
                      ).toFixed(1)}
                      %
                    </dd>
                  </div>
                </dl>
              ) : null}
              <Table
                dense
                columns={["ID", "Name", "Host market", "Sales", "Margin"]}
              >
                {simulation.stores
                  .filter((store) =>
                    simulation.similar_market_profile?.store_ids.includes(store.store_id),
                  )
                  .map((store) => (
                    <tr key={store.store_id} className="border-b border-slate-100">
                      <Cell>{store.store_id}</Cell>
                      <Cell>{store.name}</Cell>
                      <Cell>{store.host_name ?? "—"}</Cell>
                      <Cell>{formatUsd(store.annual_sales_usd)}</Cell>
                      <Cell>{store.gross_margin_pct.toFixed(1)}%</Cell>
                    </tr>
                  ))}
              </Table>
            </Card>
          ) : null}

          <Card title="Full simulated store list">
            <Table
              dense
              columns={[
                "ID",
                "Name",
                "Format",
                "City",
                "Host archetype",
                "Sales",
                "Margin",
              ]}
            >
              {simulation.stores.map((store) => (
                <tr key={store.store_id} className="border-b border-slate-100">
                  <Cell>{store.store_id}</Cell>
                  <Cell>{store.name}</Cell>
                  <Cell>{store.format}</Cell>
                  <Cell>
                    {store.city}, {store.state}
                  </Cell>
                  <Cell>{store.host_cluster_id ?? "—"}</Cell>
                  <Cell>{formatUsd(store.annual_sales_usd)}</Cell>
                  <Cell>{store.gross_margin_pct.toFixed(1)}%</Cell>
                </tr>
              ))}
            </Table>
          </Card>
        </>
      ) : (
        <EmptyState>
          No simulation yet. Adjust scenario inputs and click Run simulation.
        </EmptyState>
      )}
    </div>
  );
}
