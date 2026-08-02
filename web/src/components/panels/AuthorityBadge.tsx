"use client";

import { useSession } from "@/lib/session";
import type { TraceAuthority } from "@/lib/types";
import { Badge, type Tone } from "../ui";

/**
 * Colour carries the distinction the trace exists to make: who is answerable for a step.
 * Calculation and API evidence are the two authorities a reader should be able to trust
 * without further thought, so they are green; agent inference is amber because it is the
 * one that needed checking.
 */
const AUTHORITY_TONE: Record<TraceAuthority, Tone> = {
  user_supplied: "accent",
  agent_inference: "warning",
  deterministic_validation: "neutral",
  api_evidence: "positive",
  human_approval: "accent",
  deterministic_calculation: "positive",
  explanation_layer: "neutral",
  system: "neutral",
};

export function AuthorityBadge({ authority }: { authority: TraceAuthority }) {
  const { catalog } = useSession();
  const label = catalog?.authority_labels?.[authority] ?? authority;
  return <Badge tone={AUTHORITY_TONE[authority] ?? "neutral"}>{label}</Badge>;
}
