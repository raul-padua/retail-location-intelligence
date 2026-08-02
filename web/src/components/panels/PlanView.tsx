"use client";

/**
 * The proposal, rendered for a human who has to decide whether to authorize it.
 *
 * The organising idea is that nothing the planner did should be implicit. Every profile
 * field shows where its value came from, every weight shows why it moved, every
 * assumption shows its basis and what would reverse it, and anything the model tried to
 * say that validation threw out is shown rather than quietly dropped.
 */

import { PROVENANCE_LABELS, PROVENANCE_TONE, categoryColor, percent, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Plan } from "@/lib/types";
import { Badge, Cell, Disclosure, SectionHeading, Table } from "../ui";

const STATUS_TONE: Record<string, "positive" | "warning" | "negative" | "neutral"> = {
  approved: "positive",
  executed: "positive",
  ready_for_review: "accent" as never,
  needs_clarification: "warning",
  rejected: "negative",
  superseded: "neutral",
  draft: "neutral",
};

export function PlanView({ plan, compact }: { plan: Plan; compact?: boolean }) {
  const { catalog } = useSession();
  const categories = catalog?.categories ?? [];
  const metricsById = new Map(
    (catalog?.metrics ?? []).map((metric) => [metric.metric_id, metric]),
  );

  const weights = categories
    .map((category) => ({
      ...category,
      weight: plan.category_weights[category.id] ?? 0,
    }))
    .filter((entry) => entry.weight > 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={STATUS_TONE[plan.status] ?? "neutral"}>
          {titleCase(plan.status)}
        </Badge>
        <Badge>Version {plan.version}</Badge>
        <Badge>{plan.candidate_geographies.length} regions</Badge>
        <Badge>{plan.selected_metric_ids.length} metrics</Badge>
        <Badge tone={plan.planner_provenance.is_deterministic ? "neutral" : "accent"}>
          {plan.planner_provenance.is_deterministic
            ? "Deterministic planner"
            : `Model: ${plan.planner_provenance.model ?? "unknown"}`}
        </Badge>
      </div>

      {plan.planner_rationale ? (
        <p className="text-sm leading-relaxed text-slate-700">
          {plan.planner_rationale}
        </p>
      ) : null}

      <div>
        <SectionHeading hint="Where each value came from. An inferred value is the planner's guess, not something you said.">
          Interpreted retailer profile
        </SectionHeading>
        <Table columns={["Field", "Value", "Source"]} dense>
          {plan.profile_rows.map((row) => (
            <tr key={row.name}>
              <Cell className="font-medium text-slate-900">{row.label}</Cell>
              <Cell>
                {row.value ?? (
                  <span className="text-slate-400">Not established</span>
                )}
                {row.note ? (
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {row.note}
                  </span>
                ) : null}
              </Cell>
              <Cell>
                <Badge tone={PROVENANCE_TONE[row.provenance]}>
                  {PROVENANCE_LABELS[row.provenance]}
                </Badge>
              </Cell>
            </tr>
          ))}
        </Table>
      </div>

      <div>
        <SectionHeading hint="Proposed, not fixed. You can change these before approving.">
          Proposed category weights
        </SectionHeading>
        <div className="space-y-2">
          {weights.map((entry) => (
            <div key={entry.id} className="flex items-center gap-3">
              <span className="w-44 shrink-0 text-sm text-slate-700">
                {entry.label}
              </span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${entry.weight * 100}%`,
                    backgroundColor: categoryColor(entry.id),
                  }}
                />
              </div>
              <span className="w-14 shrink-0 text-right text-sm tabular-nums text-slate-600">
                {percent(entry.weight, 1)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SectionHeading>Candidate regions</SectionHeading>
          <ul className="space-y-1 text-sm text-slate-700">
            {plan.candidate_geographies.map((geography) => (
              <li key={geography.slug}>• {geography.display_name}</li>
            ))}
          </ul>
        </div>
        <div>
          <SectionHeading>What you will get</SectionHeading>
          <ul className="space-y-1 text-sm text-slate-700">
            {plan.expected_outputs.map((output) => (
              <li key={output}>• {output}</li>
            ))}
          </ul>
        </div>
      </div>

      {!compact && plan.selected_metric_ids.length ? (
        <Disclosure summary={`Selected metrics (${plan.selected_metric_ids.length})`}>
          <Table columns={["Metric", "Category", "Direction", "Why it may matter"]} dense>
            {plan.selected_metric_ids.map((metricId) => {
              const metric = metricsById.get(metricId);
              if (!metric) {
                return (
                  <tr key={metricId}>
                    <Cell colSpan={4}>{metricId}</Cell>
                  </tr>
                );
              }
              return (
                <tr key={metricId}>
                  <Cell className="font-medium text-slate-900">
                    {metric.display_name}
                  </Cell>
                  <Cell>{metric.category_label}</Cell>
                  <Cell>{titleCase(metric.direction)}</Cell>
                  <Cell className="text-slate-600">{metric.retail_rationale}</Cell>
                </tr>
              );
            })}
          </Table>
        </Disclosure>
      ) : null}

      {plan.assumptions.length ? (
        <div>
          <SectionHeading hint="Stated so you can overrule them, rather than folded silently into the result.">
            Assumptions
          </SectionHeading>
          <ul className="space-y-2">
            {plan.assumptions.map((assumption, index) => (
              <li
                key={`${assumption.subject}-${index}`}
                className="rounded-lg bg-amber-50 px-3 py-2 text-sm ring-1 ring-inset ring-amber-200"
              >
                <span className="font-medium text-amber-900">
                  {assumption.subject}:
                </span>{" "}
                <span className="text-amber-900">{assumption.assumption}</span>
                <span className="mt-0.5 block text-xs text-amber-800">
                  {assumption.basis}
                  {assumption.reversible_by
                    ? ` Reversible by: ${assumption.reversible_by}`
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {plan.unsupported_requirements.length ? (
        <div>
          <SectionHeading hint="Requested, and genuinely absent. No proxy was substituted.">
            Data Atlas cannot provide
          </SectionHeading>
          <ul className="space-y-2">
            {plan.unsupported_requirements.map((requirement) => (
              <li
                key={requirement.requirement}
                className="rounded-lg bg-rose-50 px-3 py-2 text-sm ring-1 ring-inset ring-rose-200"
              >
                <span className="font-medium text-rose-900">
                  {titleCase(requirement.requirement)}
                </span>
                <span className="mt-0.5 block text-xs text-rose-800">
                  {requirement.why_unavailable} Would require:{" "}
                  {requirement.would_require}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {plan.clarification_questions.some((question) => question.answer) ? (
        <div>
          <SectionHeading>Your answers</SectionHeading>
          <ul className="space-y-1 text-sm text-slate-700">
            {plan.clarification_questions
              .filter((question) => question.answer)
              .map((question) => (
                <li key={question.question_id}>
                  <span className="text-slate-500">{question.question}</span>{" "}
                  <span className="font-medium">{question.answer}</span>
                </li>
              ))}
          </ul>
        </div>
      ) : null}

      {plan.validation.disclosures.length || plan.validation.warnings.length ? (
        <div className="space-y-1 text-sm">
          {plan.validation.disclosures.map((note) => (
            <p key={note} className="text-slate-600">
              • {note}
            </p>
          ))}
          {plan.validation.warnings.map((note) => (
            <p key={note} className="text-amber-800">
              ⚠ {note}
            </p>
          ))}
        </div>
      ) : null}

      {plan.planner_provenance.rejected_fields.length ? (
        <Disclosure
          summary={`Planner output rejected by validation (${plan.planner_provenance.rejected_fields.length})`}
        >
          <p className="mb-3 text-sm text-slate-600">
            The model proposed these and deterministic validation threw them out. They are
            shown rather than hidden, because a silent rejection is indistinguishable from
            the model never having tried.
          </p>
          <Table columns={["Field", "Offending value", "Reason"]} dense>
            {plan.planner_provenance.rejected_fields.map((field, index) => (
              <tr key={`${field.field}-${index}`}>
                <Cell className="font-medium">{field.field}</Cell>
                <Cell className="font-mono text-xs">{field.offending_value}</Cell>
                <Cell className="text-slate-600">{field.reason}</Cell>
              </tr>
            ))}
          </Table>
        </Disclosure>
      ) : null}

      <div className="rounded-lg bg-slate-50 px-4 py-3 text-xs leading-relaxed text-slate-600">
        <p className="font-medium text-slate-700">This analysis will not conclude:</p>
        <ul className="mt-1 space-y-0.5">
          <li>• That any region will be profitable for your business.</li>
          <li>• That these indicators cause store performance.</li>
          <li>• Anything about rent, foot traffic, competitors, or cannibalization.</li>
          <li>• A financial forecast of any kind.</li>
        </ul>
      </div>
    </div>
  );
}
