"use client";

/**
 * Visible data-class label. Every analytical number that can cross ATLAS / PUBLIC /
 * SIMULATED boundaries should wear one of these; the badge is the UI half of the
 * ``DataClass`` enum on the wire.
 */

import clsx from "clsx";

import type { DataClass, DataClassBadge } from "@/lib/types";
import { Badge, type Tone } from "./ui";

const TONE_BY_CLASS: Record<DataClass, Tone> = {
  atlas_evidence: "positive",
  public_market_data: "accent",
  public_company_benchmark: "accent",
  simulated_retailer_data: "warning",
  user_supplied_proprietary_data: "neutral",
  user_assumption: "neutral",
  agent_interpretation: "neutral",
};

export function ProvenanceBadge({
  badge,
  className,
  showNote = false,
}: {
  badge: DataClassBadge | null | undefined;
  className?: string;
  showNote?: boolean;
}) {
  if (!badge) return null;
  return (
    <span className={clsx("inline-flex flex-col gap-0.5", className)}>
      <Badge tone={TONE_BY_CLASS[badge.data_class] ?? "neutral"}>{badge.label}</Badge>
      {showNote ? (
        <span className="max-w-xs text-[11px] leading-snug text-slate-500">
          {badge.short_note}
        </span>
      ) : null}
    </span>
  );
}
