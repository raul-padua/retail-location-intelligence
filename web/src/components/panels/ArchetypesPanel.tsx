"use client";

/**
 * Market archetypes from the frozen public-county clustering artifact.
 *
 * Membership and cluster centroids are server-computed. This panel visualizes the
 * K-means formulations (centroid feature profiles) rather than a PCA scatter, and
 * never re-clusters in the browser.
 */

import { useEffect, useMemo, useState } from "react";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, ApiError } from "@/lib/api";
import { colorForCluster } from "@/lib/archetypeColors";
import { useSelection } from "@/lib/selection";
import type {
  ArchetypeCluster,
  MarketArchetypeProfile,
  MarketDiscoveryArtifact,
} from "@/lib/types";
import { ProvenanceBadge } from "../ProvenanceBadge";
import { Badge, Banner, Card, Disclosure, EmptyState, SectionHeading } from "../ui";

function formatFeature(featureId: string, value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (featureId.includes("pct") || featureId.includes("participation")) {
    return `${value.toFixed(1)}%`;
  }
  if (featureId.includes("income")) {
    return `$${Math.round(value).toLocaleString("en-US")}`;
  }
  if (featureId === "population_total") {
    return Math.round(value).toLocaleString("en-US");
  }
  if (featureId === "population_density") {
    return `${Math.round(value).toLocaleString("en-US")}/sq mi`;
  }
  return value.toFixed(1);
}

/** Compact axis labels for the centroid comparison chart. */
function shortFeatureName(featureId: string, displayName: string): string {
  const map: Record<string, string> = {
    population_total: "Population",
    population_density: "Density",
    median_household_income: "Income",
    pct_bachelor_or_higher: "Bachelor+",
    median_age: "Median age",
    pct_age_25_44: "Age 25–44",
    pct_owner_occupied: "Owner-occ.",
    mean_commute_minutes: "Commute",
    labor_force_participation: "Labor force",
  };
  return map[featureId] ?? displayName;
}

export function ArchetypesPanel() {
  const { selectedSlug } = useSelection();
  const [artifact, setArtifact] = useState<MarketDiscoveryArtifact | null>(null);
  const [clusters, setClusters] = useState<ArchetypeCluster[]>([]);
  const [profile, setProfile] = useState<MarketArchetypeProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const clusterPayload = await api.marketDiscoveryClusters();
        if (cancelled) return;
        setArtifact(clusterPayload.artifact);
        setClusters(clusterPayload.clusters);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load archetypes.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const slug = selectedSlug;
    let cancelled = false;
    async function loadProfile() {
      if (!slug) return;
      try {
        const result = await api.marketDiscoveryMarket(slug);
        if (!cancelled) {
          setProfile(result);
          setProfileError(null);
        }
      } catch (err) {
        if (cancelled) return;
        setProfile(null);
        if (err instanceof ApiError && err.status === 422) {
          setProfileError(err.message);
        } else if (err instanceof ApiError && err.status === 404) {
          setProfileError("No county archetype is available for this geography.");
        } else {
          setProfileError(
            err instanceof ApiError ? err.message : "Failed to load market profile.",
          );
        }
      }
    }
    void loadProfile();
    return () => {
      cancelled = true;
    };
  }, [selectedSlug]);

  const visibleProfile = selectedSlug ? profile : null;
  const visibleProfileError = selectedSlug ? profileError : null;

  const featureNames = useMemo(() => {
    const map = new Map(
      (artifact?.features ?? []).map((feature) => [
        feature.feature_id,
        feature.display_name,
      ]),
    );
    return map;
  }, [artifact]);

  const formulationChart = useMemo(() => {
    const featureIds = artifact?.feature_ids ?? [];
    if (!featureIds.length || !clusters.length) return [];

    // Index each feature on a 0–100 scale across cluster centroids so bars are comparable
    // without implying absolute units on a shared axis.
    const mins: Record<string, number> = {};
    const maxs: Record<string, number> = {};
    for (const featureId of featureIds) {
      const values = clusters.map((cluster) => cluster.centroid_features[featureId] ?? 0);
      mins[featureId] = Math.min(...values);
      maxs[featureId] = Math.max(...values);
    }

    return featureIds.map((featureId) => {
      const row: Record<string, string | number> = {
        feature: shortFeatureName(
          featureId,
          featureNames.get(featureId) ?? featureId,
        ),
        featureId,
      };
      for (const cluster of clusters) {
        const raw = cluster.centroid_features[featureId] ?? 0;
        const span = maxs[featureId] - mins[featureId];
        row[cluster.cluster_id] = span <= 0 ? 50 : ((raw - mins[featureId]) / span) * 100;
        row[`${cluster.cluster_id}_raw`] = raw;
      }
      return row;
    });
  }, [artifact?.feature_ids, clusters, featureNames]);

  if (loading) {
    return <EmptyState>Loading public-market archetypes…</EmptyState>;
  }

  if (error) {
    return (
      <Banner tone="negative" title="Archetypes unavailable">
        {error}
      </Banner>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <SectionHeading>Market archetypes</SectionHeading>
          <p className="mt-1 max-w-xl text-sm text-slate-600">
            Counties are grouped by K-means into market types. Each archetype is defined by
            its average public features — not by store sales or ROI.
          </p>
        </div>
        <ProvenanceBadge badge={artifact?.data_class} showNote />
      </div>

      {artifact ? (
        <p className="text-xs text-slate-500">
          Artifact {artifact.artifact_version} · k={artifact.k} · seed={artifact.seed} ·{" "}
          {artifact.n_counties_fit} counties in fit (≥
          {artifact.min_population.toLocaleString("en-US")})
        </p>
      ) : null}

      {visibleProfileError ? (
        <Banner tone="accent" title="Selection has no county archetype">
          {visibleProfileError}
        </Banner>
      ) : null}

      {visibleProfile ? (
        <Card
          title={`${visibleProfile.name}`}
          description={`Belongs to ${visibleProfile.cluster_id} · ${visibleProfile.label}`}
          actions={
            <Badge tone="accent">
              {visibleProfile.assignment_method.replaceAll("_", " ")}
            </Badge>
          }
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                This market’s public features
              </h4>
              <ul className="mt-2 space-y-1.5 text-sm">
                {Object.entries(visibleProfile.profile).map(([featureId, value]) => (
                  <li key={featureId} className="flex justify-between gap-3">
                    <span className="text-slate-600">
                      {featureNames.get(featureId) ?? featureId}
                    </span>
                    <span className="font-medium text-slate-900">
                      {formatFeature(featureId, value)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Nearest peer counties
              </h4>
              <ul className="mt-2 space-y-1.5 text-sm">
                {visibleProfile.nearest_markets.map((peer) => (
                  <li key={peer.geoid} className="flex justify-between gap-3">
                    <span className="text-slate-700">
                      <span
                        className="mr-1.5 inline-block h-2 w-2 rounded-full"
                        style={{ background: colorForCluster(peer.cluster_id) }}
                      />
                      {peer.name}
                    </span>
                    <span className="text-slate-500">{peer.cluster_id}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {visibleProfile.caveats.length ? (
            <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-slate-500">
              {visibleProfile.caveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : null}

      <Card
        title="How each archetype is formulated"
        description="Bars compare each K-means cluster’s average (centroid) on the public features used for clustering. Values are scaled 0–100 across archetypes for readability; hover for the raw centroid value."
      >
        <div className="mb-4 flex flex-wrap gap-3">
          {clusters.map((cluster) => (
            <span key={cluster.cluster_id} className="inline-flex items-center gap-1.5 text-xs">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: colorForCluster(cluster.cluster_id) }}
              />
              {cluster.cluster_id} · {cluster.label}
            </span>
          ))}
        </div>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={formulationChart} layout="vertical" margin={{ left: 8, right: 12 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" domain={[0, 100]} hide />
              <YAxis
                type="category"
                dataKey="feature"
                width={88}
                tick={{ fontSize: 11 }}
              />
              <Tooltip
                formatter={(value, name, item) => {
                  const featureId = String(
                    (item?.payload as { featureId?: string } | undefined)?.featureId ?? "",
                  );
                  const rawKey = `${String(name)}_raw`;
                  const raw = (item?.payload as Record<string, unknown> | undefined)?.[
                    rawKey
                  ];
                  return [
                    typeof raw === "number"
                      ? formatFeature(featureId, raw)
                      : typeof value === "number"
                        ? value.toFixed(0)
                        : String(value),
                    String(name),
                  ];
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {clusters.map((cluster) => (
                <Bar
                  key={cluster.cluster_id}
                  dataKey={cluster.cluster_id}
                  fill={colorForCluster(cluster.cluster_id)}
                  radius={[0, 3, 3, 0]}
                  maxBarSize={14}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card
        title="Archetype cards"
        description="What stands out in each cluster versus the overall county set."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {clusters.map((cluster) => (
            <div
              key={cluster.cluster_id}
              className="rounded-lg border border-slate-200 bg-slate-50/80 p-3"
            >
              <div className="flex items-center gap-2">
                <span
                  className="h-3 w-3 rounded-full"
                  style={{ background: colorForCluster(cluster.cluster_id) }}
                />
                <h4 className="text-sm font-semibold text-slate-900">
                  {cluster.cluster_id} · {cluster.label}
                </h4>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {cluster.member_count} counties in fit universe
              </p>
              <p className="mt-2 text-xs text-slate-600">
                Higher than average:{" "}
                {cluster.distinctive_high
                  .map((id) => featureNames.get(id) ?? id)
                  .join(", ") || "—"}
              </p>
              <p className="text-xs text-slate-600">
                Lower than average:{" "}
                {cluster.distinctive_low
                  .map((id) => featureNames.get(id) ?? id)
                  .join(", ") || "—"}
              </p>
            </div>
          ))}
        </div>
      </Card>

      <Disclosure summary="Methodology & provenance">
        <div className="space-y-2 text-sm text-slate-600">
          <p>
            Features are ACS-shaped public-market quantities with fixed transforms, median
            imputation, z-score scaling, and correlation pruning. K-means runs over k∈[4,8]
            with a fixed seed; silhouette selects k; cluster ids are canonicalized to
            A01…A0k. The chart above shows those cluster centroids — the actual
            formulation of each archetype — rather than a PCA projection of the same
            space.
          </p>
          {artifact?.provenance_notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
          <p>
            See <code className="font-mono text-xs">docs/clustering_methodology.md</code>{" "}
            and <code className="font-mono text-xs">docs/market_discovery.md</code>.
          </p>
        </div>
      </Disclosure>
    </div>
  );
}
