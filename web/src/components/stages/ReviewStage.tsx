"use client";

/**
 * Steps 3 and 4. Review the proposal, edit it, then authorize it.
 *
 * Category weights and selected metrics are editable in place on the plan itself — those
 * are the controls people reach for first. Candidate regions stay behind a secondary
 * editor because changing the geography set is a larger decision.
 *
 * The approve button is disabled from `plan.can_approve`, which the server computes.
 * Editing does not bypass that: an edit goes back through the same validator, so pushing
 * a weight to zero or removing every metric produces a plan that cannot be approved
 * rather than one that runs and produces nonsense.
 */

import { useMemo, useState } from "react";

import { useSession } from "@/lib/session";
import { Badge, Banner, Button, Card, Field } from "../ui";
import { PlanView } from "../panels/PlanView";
import { PlanningTrace } from "../panels/PlanningTrace";

function weightsEqual(
  left: Record<string, number>,
  right: Record<string, number>,
): boolean {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) {
    if (Math.abs((left[key] ?? 0) - (right[key] ?? 0)) > 0.0005) return false;
  }
  return true;
}

function listsEqual(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
}

export function ReviewStage() {
  const { state, catalog, approve, reject, edit, backToQuestions, busy } =
    useSession();
  const plan = state?.plan;
  const [editingRegions, setEditingRegions] = useState(false);

  // null means "show the server's plan as-is". A draft is only held while the user is
  // changing controls; once the edit is applied (or the plan is replaced), we drop it.
  const [draftWeights, setDraftWeights] = useState<Record<string, number> | null>(
    null,
  );
  const [draftMetrics, setDraftMetrics] = useState<string[] | null>(null);
  const [regions, setRegions] = useState<string[] | null>(null);

  const weights = useMemo(
    () => draftWeights ?? plan?.category_weights ?? {},
    [draftWeights, plan?.category_weights],
  );
  const weightsDirty = useMemo(
    () =>
      plan != null &&
      draftWeights != null &&
      !weightsEqual(draftWeights, plan.category_weights),
    [draftWeights, plan],
  );

  const selectedMetrics = draftMetrics ?? plan?.selected_metric_ids ?? [];
  const metricsDirty = useMemo(
    () =>
      plan != null &&
      draftMetrics != null &&
      !listsEqual(draftMetrics, plan.selected_metric_ids),
    [draftMetrics, plan],
  );

  const planDirty = weightsDirty || metricsDirty;

  if (!plan) return null;

  const selectedRegions =
    regions ?? plan.candidate_geographies.map((geography) => geography.slug);

  const applyWeights = async () => {
    await edit({ categoryWeights: weights });
    setDraftWeights(null);
  };

  const applyMetrics = async () => {
    await edit({ selectedMetricIds: selectedMetrics });
    setDraftMetrics(null);
  };

  const applyRegionEdits = async () => {
    await edit({ geographies: selectedRegions });
    setRegions(null);
    setEditingRegions(false);
  };

  const approveAndRun = async () => {
    // Unsaved slider / checkbox moves should not be silently discarded under Approve.
    // Apply them first so the analysis that runs is the one the user is looking at.
    if (weightsDirty || metricsDirty) {
      await edit({
        categoryWeights: weightsDirty ? weights : undefined,
        selectedMetricIds: metricsDirty ? selectedMetrics : undefined,
      });
      setDraftWeights(null);
      setDraftMetrics(null);
    }
    await approve();
  };

  const approveLabel = busy
    ? "Running…"
    : planDirty
      ? "Apply edits and run the analysis"
      : "Approve and run the analysis";

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
        <PlanView
          plan={plan}
          weightEditor={{
            values: weights,
            onChange: setDraftWeights,
            onApply: () => void applyWeights(),
            dirty: weightsDirty,
            busy,
          }}
          metricEditor={{
            values: selectedMetrics,
            onChange: setDraftMetrics,
            onApply: () => void applyMetrics(),
            dirty: metricsDirty,
            busy,
          }}
        />
      </Card>

      <Card
        title="Edit candidate regions"
        description="Weights and metrics are editable above. Changing the geography set is a larger decision, so it lives here. Every edit is recorded and re-validated."
        actions={
          <Button
            onClick={
              editingRegions
                ? () => {
                    setEditingRegions(false);
                    setRegions(null);
                  }
                : () => {
                    setRegions(
                      plan.candidate_geographies.map((geography) => geography.slug),
                    );
                    setEditingRegions(true);
                  }
            }
          >
            {editingRegions ? "Cancel" : "Edit regions"}
          </Button>
        }
      >
        {editingRegions ? (
          <div className="space-y-5">
            <Field
              label="Candidate regions"
              hint={`${selectedRegions.length} selected. Two or more are required to compare.`}
            >
              <div className="grid max-h-40 grid-cols-1 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                {catalog?.geographies.map((geography) => (
                  <label
                    key={geography.slug}
                    className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedRegions.includes(geography.slug)}
                      onChange={() =>
                        setRegions((current) => {
                          const base =
                            current ??
                            plan.candidate_geographies.map((entry) => entry.slug);
                          return base.includes(geography.slug)
                            ? base.filter((entry) => entry !== geography.slug)
                            : [...base, geography.slug];
                        })
                      }
                    />
                    <span className="truncate">{geography.display_name}</span>
                  </label>
                ))}
              </div>
            </Field>

            <Button
              variant="primary"
              onClick={() => void applyRegionEdits()}
              disabled={busy || selectedRegions.length < 2}
            >
              Apply region changes
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
              ? planDirty
                ? "Applies your unsaved weight and metric changes, then runs the analysis."
                : undefined
              : "This plan has not passed deterministic validation."
          }
          onClick={() => void approveAndRun()}
        >
          {approveLabel}
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
