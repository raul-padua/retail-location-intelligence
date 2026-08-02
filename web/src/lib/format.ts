/**
 * Display formatting. Presentation only - nothing here changes a value's meaning.
 */

import type { LimitationSeverity, Provenance, ValidationStatus } from "./types";

export function formatValue(value: number | null, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  switch (unit) {
    case "percent":
      return `${(value * 100).toFixed(1)}%`;
    case "usd":
      return `$${Math.round(value).toLocaleString("en-US")}`;
    case "years":
      return `${value.toFixed(1)} yrs`;
    case "minutes":
      return `${value.toFixed(1)} min`;
    default:
      return Math.round(value).toLocaleString("en-US");
  }
}

export function score(value: number | null, digits = 1): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

export function percent(value: number | null, digits = 0): string {
  return value === null || value === undefined
    ? "—"
    : `${(value * 100).toFixed(digits)}%`;
}

export function signedPercent(value: number | null, digits = 0): string {
  if (value === null || value === undefined) return "—";
  const rendered = `${(value * 100).toFixed(digits)}%`;
  return value > 0 ? `+${rendered}` : rendered;
}

export function signed(value: number | null, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const rendered = value.toFixed(digits);
  return value > 0 ? `+${rendered}` : rendered;
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function sentenceCase(value: string): string {
  const spaced = value.replace(/[_-]/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export const VALIDATION_LABELS: Record<ValidationStatus, string> = {
  valid: "Valid",
  missing: "Missing",
  schema_invalid: "Schema invalid",
  incomparable_period: "Incomparable period",
  incomparable_geography: "Incomparable geography",
  incomparable_unit: "Incomparable unit",
  incomparable_source: "Incomparable source",
};

export const PROVENANCE_LABELS: Record<Provenance, string> = {
  user_supplied: "You said this",
  planner_inferred: "Planner inferred",
  unknown: "Not established",
  unsupported: "Not supported by the data",
};

/**
 * Provenance colouring. Inferred values are amber on purpose: an assumption the planner
 * made should not look the same as a fact the user stated.
 */
export const PROVENANCE_TONE: Record<
  Provenance,
  "positive" | "warning" | "neutral" | "negative"
> = {
  user_supplied: "positive",
  planner_inferred: "warning",
  unknown: "neutral",
  unsupported: "negative",
};

export const SEVERITY_TONE: Record<
  LimitationSeverity,
  "negative" | "warning" | "neutral"
> = {
  blocking: "negative",
  caution: "warning",
  info: "neutral",
};

export const SEVERITY_ORDER: Record<LimitationSeverity, number> = {
  blocking: 0,
  caution: 1,
  info: 2,
};

/** Deterministic colours for the five scoring categories, used across every chart. */
export const CATEGORY_COLORS: Record<string, string> = {
  market_potential: "#2563eb",
  customer_fit: "#7c3aed",
  economic_attractiveness: "#0d9488",
  accessibility: "#ea580c",
  growth_outlook: "#16a34a",
};

export function categoryColor(category: string): string {
  return CATEGORY_COLORS[category] ?? "#64748b";
}
