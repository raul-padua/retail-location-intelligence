"use client";

/**
 * MapLibre canvas for candidate markets.
 *
 * Analytical truth never lives here: markers are presentation of server-projected
 * geographies (slug, display name, optional centroid). The default basemap is a
 * street-level Carto/OSM raster style so city and county context is readable; override
 * with NEXT_PUBLIC_MAP_STYLE_URL. Tests and environments without WebGL get an accessible
 * list instead of a blank canvas.
 */

import { useEffect, useRef, useState } from "react";

import clsx from "clsx";

import { score } from "@/lib/format";
import type { MarketMarker } from "@/lib/selection";

import { resolveMapStyle } from "./basemap";

const FALLBACK_CENTER: [number, number] = [-73.2, 44.48];
const DEFAULT_ZOOM = 10.6;

export function MapCanvas({
  markers,
  selectedSlug,
  onSelect,
  className,
  forceFallback = false,
}: {
  markers: MarketMarker[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  className?: string;
  forceFallback?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("maplibre-gl").Map | null>(null);
  const onSelectRef = useRef(onSelect);
  const [mountFailed, setMountFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const showFallback = forceFallback || mountFailed;

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (forceFallback) return;

    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let resizeObserver: ResizeObserver | null = null;

    async function mount() {
      try {
        const maplibre = await import("maplibre-gl");
        await import("maplibre-gl/dist/maplibre-gl.css");
        if (cancelled || !containerRef.current) return;

        const map = new maplibre.Map({
          container: containerRef.current,
          style: resolveMapStyle(),
          center: FALLBACK_CENTER,
          zoom: DEFAULT_ZOOM,
          minZoom: 7,
          maxZoom: 16,
          attributionControl: {},
          failIfMajorPerformanceCaveat: false,
        });
        map.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
        mapRef.current = map;

        const reveal = () => {
          if (cancelled) return;
          map.resize();
          setReady(true);
          setMountFailed(false);
        };
        map.once("load", reveal);
        map.once("idle", () => {
          if (!cancelled) map.resize();
        });

        map.on("error", (event) => {
          const error = event.error as { message?: string; status?: number } | undefined;
          const message = String(error?.message ?? event.error ?? "");
          const styleBroken =
            !map.isStyleLoaded() &&
            (/Failed to fetch|style\.json|AJAXError|NetworkError/i.test(message) ||
              (typeof error?.status === "number" && error.status >= 400));
          if (styleBroken && !cancelled) {
            setMountFailed(true);
          }
        });

        resizeObserver = new ResizeObserver(() => {
          if (!cancelled && mapRef.current) mapRef.current.resize();
        });
        resizeObserver.observe(containerRef.current);
      } catch {
        if (!cancelled) setMountFailed(true);
      }
    }

    void mount();
    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      mapRef.current?.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [forceFallback]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || showFallback) return;

    const withCoords = markers.filter(
      (marker) => marker.geography.lat != null && marker.geography.lon != null,
    );

    const sourceId = "candidate-markets";
    const data = {
      type: "FeatureCollection" as const,
      features: withCoords.map((marker) => ({
        type: "Feature" as const,
        properties: {
          slug: marker.geography.slug,
          name: marker.geography.display_name,
          selected: marker.geography.slug === selectedSlug,
          rank: marker.rank ?? null,
          score: marker.overall_score ?? null,
          clusterColor: marker.cluster_color ?? "#3b82f6",
        },
        geometry: {
          type: "Point" as const,
          coordinates: [marker.geography.lon as number, marker.geography.lat as number],
        },
      })),
    };

    const source = map.getSource(sourceId) as import("maplibre-gl").GeoJSONSource | undefined;
    if (source) {
      source.setData(data);
    } else {
      map.addSource(sourceId, { type: "geojson", data });
      map.addLayer({
        id: "candidate-markets-circle",
        type: "circle",
        source: sourceId,
        paint: {
          "circle-radius": [
            "case",
            ["==", ["get", "selected"], true],
            11,
            7,
          ],
          "circle-color": [
            "case",
            ["==", ["get", "selected"], true],
            "#0f172a",
            ["get", "clusterColor"],
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });
      map.on("click", "candidate-markets-circle", (event) => {
        const slug = event.features?.[0]?.properties?.slug;
        if (typeof slug === "string") onSelectRef.current(slug);
      });
      map.on("mouseenter", "candidate-markets-circle", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "candidate-markets-circle", () => {
        map.getCanvas().style.cursor = "";
      });
    }

    map.resize();

    if (withCoords.length) {
      const framing =
        withCoords.filter((marker) => marker.geography.geography_type === "city")
          .length >= 2
          ? withCoords.filter((marker) => marker.geography.geography_type === "city")
          : withCoords.filter((marker) =>
              ["city", "county"].includes(marker.geography.geography_type),
            ).length
            ? withCoords.filter((marker) =>
                ["city", "county"].includes(marker.geography.geography_type),
              )
            : withCoords;

      let minLon = Infinity;
      let minLat = Infinity;
      let maxLon = -Infinity;
      let maxLat = -Infinity;
      for (const marker of framing) {
        const lon = marker.geography.lon as number;
        const lat = marker.geography.lat as number;
        minLon = Math.min(minLon, lon);
        maxLon = Math.max(maxLon, lon);
        minLat = Math.min(minLat, lat);
        maxLat = Math.max(maxLat, lat);
      }
      const padLon = Math.max((maxLon - minLon) * 0.35, 0.04);
      const padLat = Math.max((maxLat - minLat) * 0.35, 0.03);
      map.fitBounds(
        [
          [minLon - padLon, minLat - padLat],
          [maxLon + padLon, maxLat + padLat],
        ],
        { padding: 48, maxZoom: 12.5, duration: 450 },
      );
    } else {
      map.easeTo({ center: FALLBACK_CENTER, zoom: DEFAULT_ZOOM, duration: 300 });
    }

    const selected = withCoords.find(
      (marker) => marker.geography.slug === selectedSlug,
    );
    if (selected?.geography.lat != null && selected.geography.lon != null) {
      const currentZoom = map.getZoom();
      map.easeTo({
        center: [selected.geography.lon, selected.geography.lat],
        zoom: Math.max(currentZoom, 11),
        duration: 350,
      });
    }
  }, [markers, selectedSlug, ready, showFallback]);

  if (showFallback) {
    return (
      <FallbackMap
        markers={markers}
        selectedSlug={selectedSlug}
        onSelect={onSelect}
        className={className}
      />
    );
  }

  return (
    <div
      ref={containerRef}
      className={clsx(
        "h-full min-h-[18rem] w-full overflow-hidden rounded-xl bg-slate-200",
        className,
      )}
      role="region"
      aria-label="Candidate markets map"
    />
  );
}

function FallbackMap({
  markers,
  selectedSlug,
  onSelect,
  className,
}: {
  markers: MarketMarker[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "flex h-full min-h-[18rem] flex-col rounded-xl border border-dashed border-slate-300 bg-slate-50",
        className,
      )}
      role="listbox"
      aria-label="Candidate markets (list fallback)"
    >
      <div className="border-b border-slate-200 px-4 py-2 text-xs text-slate-500">
        Map unavailable in this environment. Select a market from the list.
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto p-3">
        {markers.length === 0 ? (
          <li className="px-2 py-6 text-center text-sm text-slate-500">
            No candidate regions yet. Describe a decision and select markets to place them
            here.
          </li>
        ) : (
          markers.map((marker) => {
            const selected = marker.geography.slug === selectedSlug;
            return (
              <li key={marker.geography.slug}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => onSelect(marker.geography.slug)}
                  className={clsx(
                    "flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition",
                    selected
                      ? "bg-blue-600 text-white"
                      : "bg-white text-slate-800 ring-1 ring-slate-200 hover:bg-slate-100",
                  )}
                >
                  <span className="font-medium">{marker.geography.display_name}</span>
                  {marker.overall_score != null ? (
                    <span className="tabular-nums opacity-90">
                      {score(marker.overall_score)}
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
