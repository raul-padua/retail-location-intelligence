"use client";

import { percent, score } from "@/lib/format";
import type { AnalysisResult } from "@/lib/types";
import { Badge, Banner, Card, Disclosure, Metric, Prose, SectionHeading } from "../ui";

export function RecommendationPanel({ result }: { result: AnalysisResult }) {
  if (result.refused || !result.recommendation) {
    return <RefusedResult result={result} />;
  }

  const recommendation = result.recommendation;
  const ranked = recommendation.ranked_regions;
  const leader = ranked[0];
  const runnerUp = ranked[1];
  const margin =
    leader?.overall_score != null && runnerUp?.overall_score != null
      ? leader.overall_score - runnerUp.overall_score
      : null;

  return (
    <div className="space-y-6">
      <Card
        title="Executive recommendation"
        actions={<Badge tone="accent">{recommendation.confidence_label}</Badge>}
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Leading region"
            value={leader?.geography.display_name ?? "—"}
            hint={
              margin != null
                ? `${score(margin)} points ahead of ${runnerUp.geography.display_name}`
                : undefined
            }
          />
          <Metric
            label="Overall score"
            value={`${score(leader?.overall_score ?? null)}/100`}
            hint="Relative to the other candidates, not an absolute rating"
          />
          <Metric
            label="Evidence completeness"
            value={percent(recommendation.evidence_completeness)}
            hint="Share of planned metric-region pairs Atlas actually returned"
          />
          <Metric
            label="Reproducibility hash"
            value={
              <span className="font-mono text-sm">
                {result.reproducibility_hash ?? "—"}
              </span>
            }
            hint="Same inputs, same hash, same ranking"
          />
        </div>

        <div className="mt-5">
          <SectionHeading hint={recommendation.generated_by}>
            The reasoning
          </SectionHeading>
          <Prose text={recommendation.narrative} />
        </div>

        {recommendation.caveats.length ? (
          <div className="mt-4">
            <Disclosure
              summary={`Caveats attached to this recommendation (${recommendation.caveats.length})`}
            >
              <ul className="space-y-1.5 text-sm text-slate-700">
                {recommendation.caveats.map((caveat) => (
                  <li key={caveat}>• {caveat}</li>
                ))}
              </ul>
            </Disclosure>
          </div>
        ) : null}
      </Card>

      <Card title="Ranked candidates">
        <ol className="space-y-2">
          {ranked.map((region) => (
            <li
              key={region.geography.slug}
              className="flex items-center gap-4 rounded-lg border border-slate-200 px-4 py-3"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-700">
                {region.rank}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-slate-900">
                  {region.geography.display_name}
                </p>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-blue-600"
                    style={{ width: `${region.overall_score ?? 0}%` }}
                  />
                </div>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-lg font-semibold tabular-nums text-slate-900">
                  {score(region.overall_score)}
                </p>
                <p className="text-xs text-slate-500">
                  {percent(region.evidence_completeness)} complete
                </p>
              </div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}

function RefusedResult({ result }: { result: AnalysisResult }) {
  const refusal = result.refusal;
  return (
    <Card title="The analysis ran, and the ranking is being withheld">
      <div className="space-y-4">
        <Banner tone="warning">
          {refusal?.reason ??
            "The evidence does not support ranking these regions reliably."}
        </Banner>
        <p className="text-sm text-slate-600">
          The evidence below was retrieved and validated. What is missing is enough
          separation between the candidates to call a winner, and the sufficiency gate
          declines rather than presenting a coin flip as a recommendation.
        </p>
        {refusal?.offered_alternative ? (
          <Banner tone="accent" title="What I can do instead">
            {refusal.offered_alternative}
          </Banner>
        ) : null}
      </div>
    </Card>
  );
}
