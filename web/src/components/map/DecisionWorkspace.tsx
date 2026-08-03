"use client";

/**
 * Map-first shell: sidebar rail, map + candidate tray, intelligence panel.
 *
 * Stage content (describe / clarify / review / executed tabs) renders in the right panel.
 * The map never computes scores; it only displays server-projected markers.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { colorForCluster } from "@/lib/archetypeColors";
import { useSelection, type MarketMarker } from "@/lib/selection";
import type { ArchetypeMarket } from "@/lib/types";
import { Sidebar } from "../Sidebar";
import { CandidateTray } from "./CandidateTray";
import { IntelligencePanel } from "./IntelligencePanel";
import { MapCanvas } from "./MapCanvas";
import { ResizableSplit } from "./ResizableSplit";

export function DecisionWorkspace({
  children,
  forceMapFallback = false,
}: {
  children: ReactNode;
  forceMapFallback?: boolean;
}) {
  const { markers, selectedSlug, select } = useSelection();
  const [markets, setMarkets] = useState<ArchetypeMarket[]>([]);

  useEffect(() => {
    let cancelled = false;
    void api
      .marketDiscoveryMarkets()
      .then((payload) => {
        if (!cancelled) setMarkets(payload.markets);
      })
      .catch(() => {
        if (!cancelled) setMarkets([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const coloredMarkers = useMemo<MarketMarker[]>(() => {
    if (!markets.length) return markers;
    const bySlug = new Map<string, ArchetypeMarket>();
    for (const market of markets) {
      for (const slug of market.atlas_slugs ?? []) {
        bySlug.set(slug, market);
      }
    }
    return markers.map((marker) => {
      const match = bySlug.get(marker.geography.slug);
      if (!match) return marker;
      return {
        ...marker,
        cluster_id: match.cluster_id,
        cluster_color: colorForCluster(match.cluster_id),
      };
    });
  }, [markers, markets]);

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:flex-row lg:overflow-hidden">
      <ResizableSplit
        storageKey="rli.split.sidebar"
        defaultFraction={0.22}
        minLeftPx={220}
        minRightPx={480}
        className="min-h-screen lg:h-screen"
        left={<Sidebar />}
        right={
          <ResizableSplit
            storageKey="rli.split.map-panel"
            defaultFraction={0.58}
            minLeftPx={320}
            minRightPx={300}
            left={
              <section className="flex h-full min-h-[22rem] min-w-0 flex-1 flex-col gap-3 bg-slate-100/80 p-3 lg:min-h-0 lg:p-4">
                <div className="flex shrink-0 items-center justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">Market map</h2>
                    <p className="text-xs text-slate-500">
                      Drag the dividers to resize panels. Marker colors follow public-market
                      archetypes when available; scores come only from approved services.
                    </p>
                  </div>
                </div>
                <div className="flex min-h-[18rem] min-w-0 flex-1 flex-col">
                  <MapCanvas
                    markers={coloredMarkers}
                    selectedSlug={selectedSlug}
                    onSelect={select}
                    forceFallback={forceMapFallback}
                    className="min-h-0 flex-1"
                  />
                </div>
                <div className="shrink-0">
                  <CandidateTray />
                </div>
              </section>
            }
            right={<IntelligencePanel>{children}</IntelligencePanel>}
          />
        }
      />
    </div>
  );
}
