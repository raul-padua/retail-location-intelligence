"use client";

import { SEVERITY_ORDER, SEVERITY_TONE } from "@/lib/format";
import type { AnalysisResult } from "@/lib/types";
import { Banner, Card } from "../ui";

/** Data a real investment decision needs that no public dataset can supply. */
const RETAILER_SPECIFIC_INPUTS = [
  "Store format, footprint, and build-out cost",
  "Rent, lease terms, and construction cost by site",
  "Foot traffic and catchment behaviour",
  "Competitor locations and their formats",
  "Cannibalization against your existing store network",
  "Transaction data, basket size, and gross margin",
  "Supply-chain and distribution cost to serve",
  "An approved forecasting methodology",
];

export function LimitationsPanel({ result }: { result: AnalysisResult }) {
  const limitations = [...result.limitations].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );

  return (
    <div className="space-y-6">
      <Card
        title="Limitations"
        description="What this analysis could not do, stated at the same volume as what it could."
      >
        <div className="space-y-3">
          {limitations.map((limitation, index) => (
            <Banner
              key={`${limitation.title}-${index}`}
              tone={SEVERITY_TONE[limitation.severity]}
              title={limitation.title}
            >
              {limitation.detail}
            </Banner>
          ))}
        </div>
      </Card>

      <Card
        title="What a real site-selection decision would additionally require"
        description="None of these are in Atlas. They are listed so the gap between this prototype and an investment decision stays explicit."
      >
        <ul className="grid gap-1.5 text-sm text-slate-700 sm:grid-cols-2">
          {RETAILER_SPECIFIC_INPUTS.map((input) => (
            <li key={input}>• {input}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
