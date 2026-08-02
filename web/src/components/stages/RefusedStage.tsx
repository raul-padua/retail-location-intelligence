"use client";

/**
 * The objective was refused before a planner ran.
 *
 * A refusal is a product surface here, not an error page. It says what cannot be
 * concluded, what inputs the question would actually require, and what the system will do
 * instead — because "no" without an alternative reads as a broken tool.
 */

import { useSession } from "@/lib/session";
import { Banner, Button, Card, SectionHeading } from "../ui";
import { CapabilityList } from "../panels/CapabilityList";
import { PlanningTrace } from "../panels/PlanningTrace";

export function RefusedStage() {
  const { state, reset, busy } = useSession();
  const refusal = state?.refusal;
  if (!refusal) return null;

  return (
    <div className="space-y-6">
      <Card title="This is not something the evidence can answer">
        <div className="space-y-5">
          <Banner tone="negative">{refusal.reason}</Banner>

          {refusal.unsupported_because.length ? (
            <div>
              <SectionHeading>Why</SectionHeading>
              <ul className="space-y-1 text-sm text-slate-700">
                {refusal.unsupported_because.map((reason) => (
                  <li key={reason}>• {reason}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {refusal.required_inputs.length ? (
            <div>
              <SectionHeading hint="None of these are in Atlas, and none can be inferred from what is.">
                What a credible answer would require
              </SectionHeading>
              <ul className="grid gap-1 text-sm text-slate-700 sm:grid-cols-2">
                {refusal.required_inputs.map((input) => (
                  <li key={input}>• {input}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {refusal.offered_alternative ? (
            <Banner tone="accent" title="What I can do instead">
              {refusal.offered_alternative}
            </Banner>
          ) : null}

          <Button variant="primary" onClick={() => void reset()} disabled={busy}>
            Describe a different decision
          </Button>
        </div>
      </Card>

      <Card title="What this system can do">
        <CapabilityList />
      </Card>

      <PlanningTrace />
    </div>
  );
}
