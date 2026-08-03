"use client";

/**
 * Configuration rail: connection status, the session OpenAI key, and stage progress.
 */

import clsx from "clsx";

import { useSession } from "@/lib/session";
import { Badge, Button, Field } from "./ui";

export function Sidebar() {
  const {
    catalog,
    settings,
    state,
    openaiKey,
    setOpenaiKey,
    model,
    setModel,
    useLlm,
    setUseLlm,
    llmAvailable,
    reset,
    busy,
  } = useSession();

  const steps = catalog?.stage_steps ?? [];
  const currentIndex = steps.findIndex((step) => step.stage === state?.stage);
  const refused = state?.stage === "refused";
  const selectedModel = catalog?.llm_models.find((entry) => entry.id === model);

  return (
    <aside className="flex h-full w-full min-w-0 flex-1 flex-col gap-6 border-slate-200 bg-white p-5 lg:overflow-y-auto lg:border-r">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">
          Retail Location Intelligence
        </h1>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          The agent proposes an analysis. Deterministic services decide. You approve
          before anything runs.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Atlas connection
        </h2>
        {settings?.atlas_token_present ? (
          <Badge tone="positive">
            Token configured{settings.is_demo_token ? " (public demo)" : ""}
          </Badge>
        ) : (
          <Badge tone="negative">No Atlas token</Badge>
        )}
        <p className="text-xs leading-relaxed text-slate-500">
          {catalog?.demo_token_scope_note}
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Language model
        </h2>
        <Field
          label="OpenAI API key"
          htmlFor="openai-key"
          hint="Held in this tab only. Never written to disk, logged, or included in an export."
        >
          <input
            id="openai-key"
            type="password"
            value={openaiKey}
            autoComplete="off"
            placeholder={settings?.llm_enabled ? "Set in environment" : "sk-…"}
            onChange={(event) => setOpenaiKey(event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </Field>

        {llmAvailable ? (
          <Field label="Model" htmlFor="model" hint={selectedModel?.caption}>
            <select
              id="model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            >
              {catalog?.llm_models.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.id}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <p className="text-xs leading-relaxed text-slate-500">
            No key, no problem. The planner, narrator, and assistant all fall back to
            their deterministic implementations.
          </p>
        )}

        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={useLlm && llmAvailable}
            disabled={!llmAvailable}
            onChange={(event) => setUseLlm(event.target.checked)}
            className="mt-0.5"
          />
          <span>
            Use the model to interpret the objective
            <span className="mt-0.5 block text-xs text-slate-500">
              Its output is re-validated field by field either way.
            </span>
          </span>
        </label>
      </section>

      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Progress
        </h2>
        <ol className="space-y-1.5">
          {steps.map((step, index) => {
            const done = currentIndex > index && !refused;
            const active = currentIndex === index && !refused;
            return (
              <li
                key={step.stage}
                className={clsx(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
                  active && "bg-blue-50 font-medium text-blue-800",
                  done && "text-slate-500",
                  !active && !done && "text-slate-400",
                )}
              >
                <span
                  className={clsx(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs",
                    active && "bg-blue-600 text-white",
                    done && "bg-slate-200 text-slate-600",
                    !active && !done && "bg-slate-100 text-slate-400",
                  )}
                >
                  {done ? "✓" : index + 1}
                </span>
                {step.label}
              </li>
            );
          })}
        </ol>
        {refused ? (
          <Badge tone="negative">Refused before planning</Badge>
        ) : null}
      </section>

      <div className="mt-auto pt-2">
        <Button onClick={() => void reset()} disabled={busy} className="w-full">
          Start a new analysis
        </Button>
      </div>
    </aside>
  );
}
