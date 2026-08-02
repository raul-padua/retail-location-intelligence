"use client";

/**
 * A proposed change to the analysis, sitting inert until someone confirms it.
 *
 * The card exists to make one thing unmistakable: nothing has run. It shows the exact
 * before and after, states the expected effect without claiming a result, and offers a
 * confirm button that is disabled unless the revised plan passes the same deterministic
 * validation an original plan does.
 */

import { percent, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { PlanRevision } from "@/lib/types";
import { Badge, Banner, Button, Cell, Table } from "../ui";

export function RevisionCard({ revision }: { revision: PlanRevision }) {
  const { confirmRevision, discardRevision, busy } = useSession();

  const beforeWeights = revision.before_values.category_weights as
    | Record<string, number>
    | undefined;
  const afterWeights = revision.proposed_values.category_weights as
    | Record<string, number>
    | undefined;

  const beforeMetrics = revision.before_values.selected_metric_ids as
    | string[]
    | undefined;
  const afterMetrics = revision.proposed_values.selected_metric_ids as
    | string[]
    | undefined;

  const beforeRegions = revision.before_values.candidate_geographies as
    | string[]
    | undefined;
  const afterRegions = revision.proposed_values.candidate_geographies as
    | string[]
    | undefined;

  return (
    <div className="rounded-xl border-2 border-amber-300 bg-amber-50/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-amber-900">
            Proposed change to the analysis
          </h3>
          <p className="mt-0.5 text-sm text-amber-800">
            “{revision.requested_change}”
          </p>
        </div>
        <Badge tone="warning">Nothing has run yet</Badge>
      </div>

      {revision.rationale ? (
        <p className="mt-3 text-sm text-amber-900">{revision.rationale}</p>
      ) : null}

      {beforeWeights && afterWeights ? (
        <div className="mt-4 rounded-lg bg-white p-3">
          <Table columns={["Category", "Now", "Proposed", "Change"]} dense>
            {Object.keys(afterWeights).map((category) => {
              const before = beforeWeights[category] ?? 0;
              const after = afterWeights[category] ?? 0;
              const delta = after - before;
              if (Math.abs(delta) < 0.0005) return null;
              return (
                <tr key={category}>
                  <Cell className="font-medium">{titleCase(category)}</Cell>
                  <Cell numeric>{percent(before, 1)}</Cell>
                  <Cell numeric>{percent(after, 1)}</Cell>
                  <Cell numeric>
                    <span
                      className={delta > 0 ? "text-emerald-700" : "text-rose-700"}
                    >
                      {delta > 0 ? "+" : ""}
                      {(delta * 100).toFixed(1)} pts
                    </span>
                  </Cell>
                </tr>
              );
            })}
          </Table>
        </div>
      ) : null}

      {beforeMetrics && afterMetrics ? (
        <ChangeList
          label="Metrics"
          removed={beforeMetrics.filter((entry) => !afterMetrics.includes(entry))}
          added={afterMetrics.filter((entry) => !beforeMetrics.includes(entry))}
        />
      ) : null}

      {beforeRegions && afterRegions ? (
        <ChangeList
          label="Regions"
          removed={beforeRegions.filter((entry) => !afterRegions.includes(entry))}
          added={afterRegions.filter((entry) => !beforeRegions.includes(entry))}
        />
      ) : null}

      {revision.expected_effect ? (
        <p className="mt-3 text-sm text-amber-900">
          <span className="font-medium">Likely effect:</span>{" "}
          {revision.expected_effect}
        </p>
      ) : null}

      {revision.unsupported_parts.length ? (
        <div className="mt-3">
          <Banner tone="negative" title="Part of that request cannot be honoured">
            <ul className="mt-1 space-y-0.5">
              {revision.unsupported_parts.map((part) => (
                <li key={part}>• {titleCase(part)}</li>
              ))}
            </ul>
          </Banner>
        </div>
      ) : null}

      {!revision.validation.passed ? (
        <div className="mt-3">
          <Banner tone="negative" title="The revised plan fails validation">
            <ul className="mt-1 space-y-0.5">
              {revision.validation.failures.map((failure) => (
                <li key={failure.name}>• {failure.detail}</li>
              ))}
            </ul>
          </Banner>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="primary"
          disabled={busy || !revision.is_actionable}
          title={
            revision.is_actionable
              ? undefined
              : "This revision did not pass validation and cannot be run."
          }
          onClick={() => void confirmRevision()}
        >
          {busy ? "Rerunning…" : "Confirm and rerun"}
        </Button>
        <Button disabled={busy} onClick={() => void discardRevision()}>
          Discard
        </Button>
      </div>
    </div>
  );
}

function ChangeList({
  label,
  added,
  removed,
}: {
  label: string;
  added: string[];
  removed: string[];
}) {
  if (!added.length && !removed.length) return null;
  return (
    <p className="mt-3 text-sm text-amber-900">
      <span className="font-medium">{label}:</span>{" "}
      {removed.length ? <span className="text-rose-700">−{removed.join(", ")}</span> : null}
      {removed.length && added.length ? " · " : null}
      {added.length ? (
        <span className="text-emerald-700">+{added.join(", ")}</span>
      ) : null}
    </p>
  );
}
