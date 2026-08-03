"use client";

/**
 * Shared selection between the map, the candidate tray, and the intelligence panel.
 *
 * Selection is UI state, not workflow state: it never reaches the server, and clearing it
 * does not change the plan. Keeping it out of ``SessionProvider`` avoids accidental
 * coupling between "which market am I looking at" and "which analysis is authorized".
 */

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useSession } from "./session";
import type { Geography, RankedRegion } from "./types";

export interface MarketMarker {
  geography: Geography;
  rank?: number;
  overall_score?: number | null;
  evidence_completeness?: number;
  /** Presentation-only archetype color from the public-market artifact. */
  cluster_id?: string | null;
  cluster_color?: string | null;
}

interface SelectionValue {
  selectedSlug: string | null;
  select: (slug: string | null) => void;
  markers: MarketMarker[];
  selected: MarketMarker | null;
}

const SelectionContext = createContext<SelectionValue | null>(null);

function markersFromSession(
  geographies: Geography[] | undefined,
  ranked: RankedRegion[] | undefined,
  catalogGeographies: Geography[] | undefined,
): MarketMarker[] {
  if (ranked?.length) {
    return ranked.map((region) => ({
      geography: region.geography,
      rank: region.rank,
      overall_score: region.overall_score,
      evidence_completeness: region.evidence_completeness,
    }));
  }

  const bySlug = new Map(
    (catalogGeographies ?? []).map((geography) => [geography.slug, geography]),
  );
  return (geographies ?? [])
    .map((entry) => {
      if (typeof entry === "string") {
        const geography = bySlug.get(entry);
        return geography ? { geography } : null;
      }
      const enriched = bySlug.get(entry.slug) ?? entry;
      return { geography: enriched };
    })
    .filter((marker): marker is MarketMarker => marker != null);
}

export function SelectionProvider({ children }: { children: ReactNode }) {
  const { state, catalog } = useSession();
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);

  const ranked = state?.versions.at(-1)?.result.recommendation?.ranked_regions;
  const planGeographies = state?.plan?.candidate_geographies;
  const sessionSlugs = state?.geographies;

  const markers = useMemo(() => {
    if (planGeographies?.length) {
      return markersFromSession(planGeographies, ranked, catalog?.geographies);
    }
    return markersFromSession(
      sessionSlugs?.map((slug) => ({ slug, display_name: slug, geography_type: "" })),
      ranked,
      catalog?.geographies,
    );
  }, [planGeographies, ranked, sessionSlugs, catalog?.geographies]);

  // Derive the effective selection. If the user's choice is still in the candidate set,
  // keep it; otherwise fall back to the first marker. No effect-driven setState.
  const resolvedSlug = useMemo(() => {
    if (selectedSlug && markers.some((marker) => marker.geography.slug === selectedSlug)) {
      return selectedSlug;
    }
    return markers[0]?.geography.slug ?? null;
  }, [markers, selectedSlug]);

  const value = useMemo<SelectionValue>(() => {
    const selected =
      markers.find((marker) => marker.geography.slug === resolvedSlug) ?? null;
    return {
      selectedSlug: resolvedSlug,
      select: setSelectedSlug,
      markers,
      selected,
    };
  }, [markers, resolvedSlug]);

  return (
    <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>
  );
}

export function useSelection(): SelectionValue {
  const value = useContext(SelectionContext);
  if (!value) {
    throw new Error("useSelection requires SelectionProvider");
  }
  return value;
}
