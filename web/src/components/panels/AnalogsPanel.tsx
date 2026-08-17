"use client";

/**
 * Analog-store matching (Phase 4).
 *
 * Matching math runs in Python; this panel renders projections only. Performance
 * summaries are simulated NorthStar data shown after ranking.
 */

import { useEffect, useMemo, useState } from "react";

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

import { api, ApiError } from "@/lib/api";
import { useSelection } from "@/lib/selection";
import { useSession } from "@/lib/session";
import type { AnalogMatch, AnalogSearchResult, AnalogMatchingMeta } from "@/lib/types";
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
} from "../ui";

const FORMAT_OPTIONS = ["", "mall", "strip", "outlet"];

function formatUsd(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

function strengthTone(strength: AnalogSearchResult["analogy_strength"]) {
  if (strength === "strong") return "positive" as const;
  if (strength === "moderate") return "accent" as const;
  if (strength === "weak") return "warning" as const;
  return "negative" as const;
}

export function AnalogsPanel() {
  const { sessionId } = useSession();
  const { selectedSlug } = useSelection();
  const [meta, setMeta] = useState<AnalogMatchingMeta | null>(null);
  const [search, setSearch] = useState<AnalogSearchResult | null>(null);
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [topK, setTopK] = useState(5);
  const [preferredFormat, setPreferredFormat] = useState("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const metaPayload = await api.analogMatchingMeta();
        if (cancelled) return;
        setMeta(metaPayload);
        if (sessionId) {
          try {
            const last = await api.analogMatchingLast(sessionId);
            if (!cancelled) {
              setSearch(last.search);
              setSelectedMatchId(last.search.matches[0]?.store_id ?? null);
            }
          } catch (err) {
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
          setError(err instanceof ApiError ? err.message : "Failed to load analog matcher.");
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

  const runSearch = async () => {
    if (!selectedSlug) return;
    setRunning(true);
    setError(null);
    try {
      // Stateless search — does not depend on in-memory workflow sessions (important on Vercel).
      const payload = await api.analogMatchingSearch({
        market_id: selectedSlug,
        top_k: topK,
        preferred_format: preferredFormat || null,
      });
      setSearch(payload.search);
      setSelectedMatchId(payload.search.matches[0]?.store_id ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analog search failed.");
    } finally {
      setRunning(false);
    }
  };

  const selectedMatch: AnalogMatch | null = useMemo(() => {
    if (!search || !selectedMatchId) return search?.matches[0] ?? null;
    return search.matches.find((match) => match.store_id === selectedMatchId) ?? null;
  }, [search, selectedMatchId]);

  const contributionChart = useMemo(() => {
    if (!selectedMatch) return [];
    return selectedMatch.contributions.slice(0, 8).map((entry) => ({
      name: entry.display_name,
      value: entry.signed_contribution,
      fill: entry.signed_contribution >= 0 ? "#2563eb" : "#dc2626",
    }));
  }, [selectedMatch]);

  if (loading) {
    return <EmptyState>Loading analog-store matcher…</EmptyState>;
  }

  if (!selectedSlug) {
    return (
      <EmptyState>
        Select a candidate market on the map first. Analog search needs a place to compare
        against.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      <Banner tone="accent" title="What this answers">
        <p className="text-sm leading-relaxed">
          <strong>Analog stores</strong> answer a practical site-selection question:{" "}
          <em>
            “If we already had stores in markets that look like this candidate, which ones
            are the closest cousins — and how did those fictional stores perform?”
          </em>{" "}
          Public demographics find the cousins; simulated NorthStar sales are shown only
          afterward as demo context, never as a prediction for the new site.
        </p>
      </Banner>

      <Banner tone="warning" title="Simulated performance labels">
        Look-alike matching uses public market characteristics only (income, age mix, density,
        and so on). Sales or margin figures attached to a ranked analog are NorthStar Apparel
        simulated data for the demo — not observed performance from any real retailer.
      </Banner>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <SectionHeading>Analog stores</SectionHeading>
          <p className="mt-1 max-w-xl text-sm text-slate-600">
            Compare the selected candidate to fictional NorthStar stores in look-alike
            counties. Use this to tell a story about “markets like this,” not to forecast the
            new store’s sales.
          </p>
        </div>
        <ProvenanceBadge badge={search?.data_class ?? meta?.data_class} showNote />
      </div>

      {meta ? (
        <p className="text-xs text-slate-500">
          Matcher {meta.matcher_version} · features {meta.feature_set_version}
        </p>
      ) : null}

      {error ? (
        <Banner tone="negative" title="Analog search error">
          {error}
        </Banner>
      ) : null}

      <Card
        title="Find look-alike stores"
        description="Start from the market selected on the map. Optionally prefer a store format."
      >
        <p className="mb-3 text-sm text-slate-600">
          Comparing against:{" "}
          <span className="font-medium text-slate-800">{selectedSlug}</span>
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Top K matches" htmlFor="analog-top-k">
            <input
              id="analog-top-k"
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(event) => setTopK(Number(event.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Preferred format (optional soft match)" htmlFor="analog-format">
            <select
              id="analog-format"
              value={preferredFormat}
              onChange={(event) => setPreferredFormat(event.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {FORMAT_OPTIONS.map((option) => (
                <option key={option || "any"} value={option}>
                  {option || "Any format"}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="mt-4">
          <Button onClick={() => void runSearch()} disabled={running || !selectedSlug}>
            {running ? "Searching…" : "Find look-alike stores"}
          </Button>
        </div>
      </Card>

      {search ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={strengthTone(search.analogy_strength)}>
              Analogy {search.analogy_strength}
            </Badge>
            <Badge>{search.candidate_name}</Badge>
            <Badge>GEOID {search.candidate_geoid}</Badge>
            {search.aggregate_range ? (
              <Badge>
                Similarity {search.aggregate_range.min_similarity.toFixed(2)}–
                {search.aggregate_range.max_similarity.toFixed(2)}
              </Badge>
            ) : null}
          </div>

          {search.warnings.length ? (
            <Banner tone="warning" title="Analog caveats">
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                {search.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Banner>
          ) : null}

          <div className="grid gap-3 lg:grid-cols-2">
            {search.matches.map((match) => (
              <button
                key={match.store_id}
                type="button"
                onClick={() => setSelectedMatchId(match.store_id)}
                className={`rounded-lg border p-4 text-left transition ${
                  selectedMatch?.store_id === match.store_id
                    ? "border-blue-500 bg-blue-50"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{match.store_name}</span>
                  <Badge tone="accent">Similarity {match.similarity.toFixed(3)}</Badge>
                </div>
                <p className="mt-1 text-sm text-slate-600">
                  {match.format} · host {match.host_name} ({match.host_geoid})
                </p>
                {match.performance_summary ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                    <ProvenanceBadge badge={match.performance_summary.data_class} />
                    <span>
                      Simulated sales {formatUsd(match.performance_summary.median_annual_sales_usd)}
                    </span>
                    <span>
                      margin {match.performance_summary.median_gross_margin_pct.toFixed(1)}%
                    </span>
                  </div>
                ) : null}
                {match.mismatches.length ? (
                  <p className="mt-2 text-xs text-amber-700">{match.mismatches.join(" ")}</p>
                ) : null}
              </button>
            ))}
          </div>

          {selectedMatch ? (
            <Card title={`Why this is a look-alike — ${selectedMatch.store_name}`}>
              <p className="mb-3 text-sm text-slate-600">
                How each public market feature pushes the candidate toward or away from this
                store’s host county. Positive bars mean the candidate is higher on that
                feature. Sales and margin are not used in this comparison.
              </p>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={contributionChart} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={140}
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip />
                    <Bar dataKey="value">
                      {contributionChart.map((entry) => (
                        <ChartCell key={entry.name} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          ) : null}

          <Disclosure summary="Context pack (assistant-safe summary)">
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {search.context_pack.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </Disclosure>
        </>
      ) : (
        <EmptyState>
          No look-alikes yet. Choose Top K (and an optional format), then click Find
          look-alike stores.
        </EmptyState>
      )}
    </div>
  );
}
