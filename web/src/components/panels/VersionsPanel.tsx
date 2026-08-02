"use client";

/**
 * Plan lineage: what changed between two approved versions, and what it did to the answer.
 *
 * The attribution list is the part worth reading. It is produced deterministically from
 * the two plans and two results, so "the leader changed because Economic Attractiveness
 * went from 18% to 31%" is a computed statement rather than a narrated guess.
 */

import { percent, score, signed, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Badge, Banner, Card, Cell, Disclosure, EmptyState, Metric, Table } from "../ui";
import { PlanView } from "./PlanView";

export function VersionsPanel() {
  const { state } = useSession();
  const versions = state?.versions ?? [];
  const planDiff = state?.plan_diff;
  const resultDiff = state?.result_diff;

  if (versions.length < 2 || !planDiff || !resultDiff) {
    return (
      <div className="space-y-4">
        <EmptyState>
          Only one version has been executed. Ask the assistant for a change — “double the
          importance of household income” — and confirm it to produce a second.
        </EmptyState>
        {versions[0] ? (
          <Card title={`Plan ${versions[0].label}`}>
            <PlanView plan={versions[0].plan} compact />
          </Card>
        ) : null}
      </div>
    );
  }

  const previous = versions.at(-2)!;
  const current = versions.at(-1)!;

  return (
    <div className="space-y-6">
      <Banner tone={resultDiff.leader_changed ? "warning" : "positive"}>
        {resultDiff.leader_changed
          ? `The leader changed: ${resultDiff.previous_leader} → ${resultDiff.new_leader}. ` +
            (resultDiff.evidence_changed
              ? "The evidence also changed between runs."
              : "The evidence is identical; only the weighting differs.")
          : `The leader held at ${resultDiff.new_leader} across both versions.`}
      </Banner>

      <div className="grid gap-3 sm:grid-cols-3">
        <Metric
          label={`Leader, v${planDiff.from_version}`}
          value={resultDiff.previous_leader ?? "—"}
          hint={
            <span className="font-mono">
              {resultDiff.previous_hash?.slice(0, 12) ?? "—"}
            </span>
          }
        />
        <Metric
          label={`Leader, v${planDiff.to_version}`}
          value={resultDiff.new_leader ?? "—"}
          hint={
            <span className="font-mono">
              {resultDiff.new_hash?.slice(0, 12) ?? "—"}
            </span>
          }
        />
        <Metric
          label="Revision"
          value={planDiff.revision_summary ? "Applied" : "—"}
          hint={planDiff.revision_summary ?? undefined}
        />
      </div>

      {planDiff.weight_changes.length ? (
        <Card title="What changed in the plan">
          <Table columns={["Category", "Before", "After", "Change"]} dense>
            {planDiff.weight_changes.map((change) => (
              <tr key={change.category}>
                <Cell className="font-medium">{titleCase(change.category)}</Cell>
                <Cell numeric>{percent(change.before, 1)}</Cell>
                <Cell numeric>{percent(change.after, 1)}</Cell>
                <Cell numeric>
                  <span
                    className={
                      change.change > 0 ? "text-emerald-700" : "text-rose-700"
                    }
                  >
                    {signed(change.change * 100, 1)} pts
                  </span>
                </Cell>
              </tr>
            ))}
          </Table>

          {(
            [
              ["Metrics added", planDiff.metrics_added],
              ["Metrics removed", planDiff.metrics_removed],
              ["Regions added", planDiff.regions_added],
              ["Regions removed", planDiff.regions_removed],
            ] as const
          )
            .filter(([, values]) => values.length > 0)
            .map(([label, values]) => (
              <p key={label} className="mt-2 text-sm text-slate-600">
                <span className="font-medium">{label}:</span> {values.join(", ")}
              </p>
            ))}
        </Card>
      ) : null}

      <Card title="What it did to the answer">
        <Table
          columns={["Region", "Rank before", "Rank after", "Score before", "Score after", "Change"]}
          dense
        >
          {resultDiff.deltas.map((delta) => (
            <tr key={delta.slug}>
              <Cell className="font-medium">{delta.display_name}</Cell>
              <Cell numeric>{delta.baseline_rank}</Cell>
              <Cell numeric>
                {delta.comparison_rank}
                {delta.rank_change !== 0 ? (
                  <span
                    className={
                      delta.rank_change > 0
                        ? "ml-1 text-emerald-700"
                        : "ml-1 text-rose-700"
                    }
                  >
                    {delta.rank_change > 0 ? "▲" : "▼"}
                  </span>
                ) : null}
              </Cell>
              <Cell numeric>{score(delta.baseline_score)}</Cell>
              <Cell numeric>{score(delta.comparison_score)}</Cell>
              <Cell numeric>{signed(delta.score_change)}</Cell>
            </tr>
          ))}
        </Table>
      </Card>

      <Card
        title="Why the answer moved"
        description="Produced deterministically from the two plans and two results, not narrated."
      >
        <ul className="space-y-1.5 text-sm text-slate-700">
          {resultDiff.attribution.map((line, index) => (
            <li key={index}>• {line}</li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Disclosure summary={`Full plan, ${previous.label}`}>
          <PlanView plan={previous.plan} compact />
        </Disclosure>
        <Disclosure summary={`Full plan, ${current.label}`}>
          <PlanView plan={current.plan} compact />
        </Disclosure>
      </div>

      <div className="flex flex-wrap gap-2">
        {versions.map((version) => (
          <Badge
            key={version.label}
            tone={version === current ? "accent" : "neutral"}
          >
            {version.label}: {titleCase(version.plan.status)}
          </Badge>
        ))}
      </div>
    </div>
  );
}
