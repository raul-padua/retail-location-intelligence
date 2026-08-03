/**
 * Default MapLibre style: street-level detail without a paid token.
 *
 * The previous MapLibre demotiles style is intentionally sparse and reads as a
 * country overview. Carto Voyager raster tiles show cities, roads, and county
 * context for the Burlington demo footprint. Override with NEXT_PUBLIC_MAP_STYLE_URL
 * when you have a vector style of your own.
 */

export const LOCAL_DETAIL_STYLE = {
  version: 8 as const,
  name: "local-detail",
  // No glyphs/sprites: marker labels live in the candidate tray, so the style stays
  // raster-only and does not depend on a font CDN that can fail the map shell.
  sources: {
    carto: {
      type: "raster" as const,
      tiles: [
        "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
      maxzoom: 20,
    },
  },
  layers: [
    {
      id: "carto-tiles",
      type: "raster" as const,
      source: "carto",
      minzoom: 0,
      maxzoom: 22,
    },
  ],
};

export function resolveMapStyle(): string | typeof LOCAL_DETAIL_STYLE {
  const configured = process.env.NEXT_PUBLIC_MAP_STYLE_URL?.trim();
  if (configured) return configured;
  return LOCAL_DETAIL_STYLE;
}
