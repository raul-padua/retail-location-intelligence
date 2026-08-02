"use client";

/**
 * Steps 3 and 4. Review the proposal, edit it, then authorize it.
 *
 * The approve button is disabled from `plan.can_approve`, which the server computes.
 * Editing does not bypass that: an edit goes back through the same validator, so pushing
 * a weight to zero or removing every metric produces a plan that cannot be approved
 * rather than one that runs and produces nonsense.
 */

import { useMemo, useState } from "react";

import { percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Badge, Banner, Button, Card, Field } from "../ui";
import { PlanView } from "../panels/PlanView";
import { PlanningTrace } from "../panels/PlanningTrace";

export function ReviewStage() {
  const { state, catalog, approve, reject, edit, backToQuestions, busy } =
    useSession();
  const plan = state?.plan;
  const [editing, setEditing] = useState(false);

  const initialWeights = useMemo(
    () => ({ ...(plan?.category_weights ?? {}) }),
    [plan?.category_weights],
  );
  const [weights, setWeights] = useState<Record<string, number>>(initialWeights);
  const [metrics, setMetrics] = useState<string[]>(plan?.selected_metric_ids ?? []);
  const [regions, setRegions] = useState<string[]>(
    plan?.candidate_geographies.map((geography) => geography.slug) ?? [],
  );

  if (!plan) return null;

  const weightTotal = Object.values(weights).reduce((sum, value) => sum + value, 0);

  const openEditor = () => {
    setWeights({ ...plan.category_weights });
    setMetrics(plan.selected_metric_ids);
    setRegions(plan.candidate_geographies.map((geography) => geography.slug));
    setEditing(true);
  };

  const applyEdits = async () => {
    await edit({
      categoryWeights: weights,
      selectedMetricIds: metrics,
      geographies: regions,
    });
    setEditing(false);
  };

  return (
    <div className="space-y-6">
      {!plan.can_approve ? (
        <Banner tone="negative" title="This plan cannot be approved yet">
          <ul className="mt-1 space-y-1">
            {plan.validation.failures.map((failure) => (
              <li key={failure.name}>• {failure.detail}</li>
            ))}
            {plan.unanswered_required_question_ids.length ? (
              <li>• A required clarification is still unanswered.</li>
            ) : null}
          </ul>
        </Banner>
      ) : null}

      <Card
        title="Proposed analysis plan"
        description="Nothing has run. Approving this is what authorizes the Atlas calls and the scoring."
        actions={
          <Badge tone={plan.can_approve ? "positive" : "warning"}>
            {plan.can_approve ? "Passed validation" : "Blocked"}
          </Badge>
        }
      >
        <PlanView plan={plan} />
      </Card>

      <Card
        title="Edit before approving"
        description="Every edit is recorded against the plan and re-validated. It does not skip the gate."
        actions={
          <Button onClick={editing ? () => setEditing(false) : openEditor}>
            {editing ? "Cancel" : "Edit plan"}
          </Button>
        }
      >
        {editing ? (
          <div className="space-y-5">
            <Field
              label="Category weights"
              hint={`They need not sum to 1 — the server renormalizes and records the change. Current total: ${weightTotal.toFixed(2)}`}
            >
              <div className="space-y-3">
                {catalog?.categories.map((category) => (
                  <div key={category.id}>
                    <div className="flex items-center gap-3">
                      <label
                        htmlFor={`weight-${category.id}`}
                        className="w-44 shrink-0 text-sm text-slate-700"
                      >
                        {category.label}
                      </label>
                      <input
                        id={`weight-${category.id}`}
                        type="range"
                        min={0}
                        max={1}
                        step={0.01}
                        value={weights[category.id] ?? 0}
                        onChange={(event) =>
                          setWeights((current) => ({
                            ...current,
                            [category.id]: Number(event.target.value),
                          }))
                        }
                        className="flex-1"
                      />
                      <span className="w-14 shrink-0 text-right text-sm tabular-nums text-slate-600">
                        {percent(weights[category.id] ?? 0, 0)}
                      </span>
                    </div>
                    <p className="ml-44 pl-3 text-xs text-slate-500">
                      {category.guidance}
                    </p>
                  </div>
                ))}
              </div>
            </Field>

            <Field
              label="Metrics in the analysis"
              hint={`${metrics.length} selected. Only registry metrics can be added.`}
            >
              <div className="grid max-h-52 grid-cols-1 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                {catalog?.metrics.map((metric) => (
                  <label
                    key={metric.metric_id}
                    className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={metrics.includes(metric.metric_id)}
                      onChange={() =>
                        setMetrics((current) =>
                          current.includes(metric.metric_id)
                            ? current.filter((entry) => entry !== metric.metric_id)
                            : [...current, metric.metric_id],
                        )
                      }
                    />
                    <span className="truncate" title={metric.display_name}>
                      {metric.display_name}
                    </span>
                  </label>
                ))}
              </div>
            </Field>

            <Field label="Candidate regions" hint={`${regions.length} selected.`}>
              <div className="grid max-h-40 grid-cols-1 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                {catalog?.geographies.map((geography) => (
                  <label
                    key={geography.slug}
                    className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={regions.includes(geography.slug)}
                      onChange={() =>
                        setRegions((current) =>
                          current.includes(geography.slug)
                            ? current.filter((entry) => entry !== geography.slug)
                            : [...current, geography.slug],
                        )
                      }
                    />
                    <span className="truncate">{geography.display_name}</span>
                  </label>
                ))}
              </div>
            </Field>

            <Button variant="primary" onClick={() => void applyEdits()} disabled={busy}>
              Apply edits and revalidate
            </Button>
          </div>
        ) : plan.approval_record.edits.length ? (
          <ul className="space-y-1 text-sm text-slate-600">
            {plan.approval_record.edits.map((entry, index) => (
              <li key={`${entry.field}-${index}`}>
                • You changed <span className="font-medium">{entry.field}</span>.
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">
            No edits yet. The plan is exactly as the planner proposed it.
          </p>
        )}
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          disabled={busy || !state?.can_approve}
          title={
            state?.can_approve
              ? undefined
              : "This plan has not passed deterministic validation."
          }
          onClick={() => void approve()}
        >
          {busy ? "Running…" : "Approve and run the analysis"}
        </Button>
        <Button
          disabled={busy || plan.clarification_questions.length === 0}
          onClick={() => void backToQuestions()}
        >
          Back to questions
        </Button>
        <Button
          variant="danger"
          disabled={busy}
          onClick={() => void reject("rejected at review")}
        >
          Reject and start over
        </Button>
      </div>

      <PlanningTrace />
    </div>
  );
}
