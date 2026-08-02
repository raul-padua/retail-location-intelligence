"use client";

/**
 * The governed capability registry, available and unavailable side by side.
 *
 * Showing the unavailable ones is the point. An agent that silently lacks a foot-traffic
 * tool looks identical to one that has decided foot traffic does not matter; naming the
 * gap, its required inputs, and who would supply it is what makes the boundary legible.
 */

import { titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Badge, Cell, SectionHeading, Table } from "../ui";

export function CapabilityList() {
  const { catalog } = useSession();
  const capabilities = catalog?.capabilities ?? [];
  const available = capabilities.filter((entry) => entry.is_available);
  const unavailable = capabilities.filter((entry) => !entry.is_available);

  return (
    <div className="space-y-6">
      <div>
        <SectionHeading hint="Tools the agent may ask for. It cannot invoke anything outside this list.">
          Available now ({available.length})
        </SectionHeading>
        <Table columns={["Capability", "Kind", "What it does", "Deterministic"]} dense>
          {available.map((capability) => (
            <tr key={capability.capability_id}>
              <Cell className="font-medium text-slate-900">
                {capability.display_name}
              </Cell>
              <Cell>{titleCase(capability.kind)}</Cell>
              <Cell className="text-slate-600">{capability.description}</Cell>
              <Cell>
                {capability.deterministic ? (
                  <Badge tone="positive">Yes</Badge>
                ) : (
                  <Badge tone="warning">Model-assisted</Badge>
                )}
              </Cell>
            </tr>
          ))}
        </Table>
      </div>

      <div>
        <SectionHeading hint="The agent may recommend these as next steps. It will never behave as though one ran.">
          Declared unavailable ({unavailable.length})
        </SectionHeading>
        <div className="grid gap-3 sm:grid-cols-2">
          {unavailable.map((capability) => (
            <div
              key={capability.capability_id}
              className="rounded-lg border border-slate-200 bg-slate-50/60 p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-slate-900">
                  {capability.display_name}
                </p>
                <Badge tone="negative">Unavailable</Badge>
              </div>
              <p className="mt-1 text-xs text-slate-600">{capability.description}</p>
              {capability.unavailable_because ? (
                <p className="mt-1.5 text-xs text-slate-500">
                  {capability.unavailable_because}
                </p>
              ) : null}
              {capability.required_data.length ? (
                <p className="mt-1.5 text-xs text-slate-500">
                  <span className="font-medium">Would need:</span>{" "}
                  {capability.required_data.join(", ")}
                </p>
              ) : null}
              {capability.expected_provider ? (
                <p className="mt-0.5 text-xs text-slate-500">
                  <span className="font-medium">From:</span>{" "}
                  {capability.expected_provider}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
