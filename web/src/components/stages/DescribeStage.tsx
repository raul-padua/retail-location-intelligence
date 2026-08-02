"use client";

/**
 * Step 1. A free-text business objective and a set of candidate regions.
 *
 * This is the whole entry point. There is no weights panel here on purpose: weights are
 * something the planner proposes and the user reviews, not something an executive is
 * asked to set before the system has understood the question.
 */

import { useState } from "react";

import { useSession } from "@/lib/session";
import { Button, Card, Field } from "../ui";
import { CapabilityList } from "../panels/CapabilityList";

export function DescribeStage() {
  const { catalog, state, describe, busy } = useSession();
  const [objective, setObjective] = useState(state?.objective ?? "");
  const [selected, setSelected] = useState<string[]>(state?.geographies ?? []);
  const [retailerType, setRetailerType] = useState(state?.retailer_type ?? "");
  const [storeFormat, setStoreFormat] = useState(state?.store_format ?? "");
  const [targetSegments, setTargetSegments] = useState(
    state?.target_segments ?? "",
  );
  const [showProfile, setShowProfile] = useState(false);

  const toggle = (slug: string) =>
    setSelected((current) =>
      current.includes(slug)
        ? current.filter((entry) => entry !== slug)
        : [...current, slug],
    );

  return (
    <div className="space-y-6">
      <Card
        title="Describe the decision"
        description="Write it the way you would say it to a colleague. The planner reads the strategy out of the sentence."
      >
        <div className="space-y-5">
          <Field label="Start from an example" htmlFor="example">
            <select
              id="example"
              defaultValue=""
              onChange={(event) => {
                const match = catalog?.objective_examples.find(
                  (entry) => entry.label === event.target.value,
                );
                if (match) setObjective(match.objective);
              }}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">Write my own</option>
              {catalog?.objective_examples.map((entry) => (
                <option key={entry.label} value={entry.label}>
                  {entry.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Business objective" htmlFor="objective">
            <textarea
              id="objective"
              rows={4}
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              placeholder="We are evaluating Burlington, South Burlington, and Winooski for a suburban apparel store targeting middle-income families. Prioritize growth and accessibility over current market size."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-relaxed focus:border-blue-500 focus:outline-none"
            />
          </Field>

          <Field
            label="Candidate regions"
            hint={`${selected.length} selected. Two or more are required to compare anything.`}
          >
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {catalog?.presets.map((preset) => (
                  <Button
                    key={preset.label}
                    variant="ghost"
                    onClick={() => setSelected(preset.slugs)}
                    className="border border-slate-200 text-xs"
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
              <div className="grid max-h-56 grid-cols-1 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                {catalog?.geographies.map((geography) => (
                  <label
                    key={geography.slug}
                    className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(geography.slug)}
                      onChange={() => toggle(geography.slug)}
                    />
                    <span className="truncate">{geography.display_name}</span>
                  </label>
                ))}
              </div>
            </div>
          </Field>

          <div>
            <button
              type="button"
              onClick={() => setShowProfile((open) => !open)}
              className="text-sm font-medium text-blue-700 hover:underline"
            >
              {showProfile ? "Hide" : "Add"} optional retailer profile
            </button>
            {showProfile ? (
              <div className="mt-3 grid gap-4 rounded-lg border border-slate-200 p-4 sm:grid-cols-3">
                <Field label="Retailer type" htmlFor="retailer-type">
                  <input
                    id="retailer-type"
                    value={retailerType}
                    onChange={(event) => setRetailerType(event.target.value)}
                    placeholder="Mainstream apparel"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </Field>
                <Field label="Store format" htmlFor="store-format">
                  <input
                    id="store-format"
                    value={storeFormat}
                    onChange={(event) => setStoreFormat(event.target.value)}
                    placeholder="Suburban full-price"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </Field>
                <Field label="Target customers" htmlFor="segments">
                  <input
                    id="segments"
                    value={targetSegments}
                    onChange={(event) => setTargetSegments(event.target.value)}
                    placeholder="Middle-income families"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </Field>
              </div>
            ) : null}
          </div>

          <Button
            variant="primary"
            disabled={busy || objective.trim().length === 0}
            onClick={() =>
              void describe({
                objective,
                geographies: selected,
                retailerType,
                storeFormat,
                targetSegments,
              })
            }
          >
            {busy ? "Interpreting…" : "Interpret and propose a plan"}
          </Button>
        </div>
      </Card>

      <Card
        title="What this system can and cannot do"
        description="The registry of governed capabilities, including the ones that are declared unavailable."
      >
        <CapabilityList />
      </Card>
    </div>
  );
}
