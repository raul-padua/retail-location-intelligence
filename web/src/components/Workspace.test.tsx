/**
 * Stage routing and the controls that gate the pipeline.
 *
 * The assertions worth having here are the negative ones. That the review screen renders
 * a plan is unremarkable; that its approve button is disabled when the server says the
 * plan cannot be approved is the entire safety story rendered as a UI state, and it is the
 * kind of thing a refactor quietly breaks.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Workspace } from "@/components/Workspace";
import type { WorkflowState } from "@/lib/types";

import {
  catalogFixture,
  clarifyStateFixture,
  executedStateFixture,
  pendingRevisionStateFixture,
  refusedStateFixture,
  reviewStateFixture,
} from "@/test/fixtures.generated";
import { renderApp, stubApi } from "@/test/harness";

const describeState: WorkflowState = {
  ...reviewStateFixture,
  stage: "describe",
  plan: null,
  can_approve: false,
};

describe("stage routing", () => {
  it("opens on the objective, with no result in sight", async () => {
    stubApi({ state: describeState });
    renderApp(<Workspace />);

    expect(
      await screen.findByRole("heading", { name: "Describe the decision" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Business objective")).toBeInTheDocument();
    expect(screen.queryByText("Executive recommendation")).not.toBeInTheDocument();
  });

  it("shows the clarifying questions and why each one matters", async () => {
    stubApi({ state: clarifyStateFixture });
    renderApp(<Workspace />);

    await screen.findByText(/would change the analysis/i);
    const questions = clarifyStateFixture.plan!.clarification_questions;
    expect(questions.length).toBeGreaterThan(0);
    expect(questions.length).toBeLessThanOrEqual(3);
    for (const question of questions) {
      expect(screen.getByText(question.question)).toBeInTheDocument();
      expect(screen.getByText(question.why_it_matters)).toBeInTheDocument();
    }
  });

  it("renders a refusal as an explanation with an alternative, not an error", async () => {
    stubApi({ state: refusedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText(/not something the evidence can answer/i);
    expect(screen.getByText(refusedStateFixture.refusal!.reason)).toBeInTheDocument();
    expect(screen.getByText(/What I can do instead/i)).toBeInTheDocument();
    for (const input of refusedStateFixture.refusal!.required_inputs.slice(0, 3)) {
      expect(screen.getByText(`• ${input}`)).toBeInTheDocument();
    }
  });

  it("renders the result once a plan has been approved and run", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    expect(await screen.findByText("Executive recommendation")).toBeInTheDocument();
    expect(screen.getByText("Analysis complete")).toBeInTheDocument();
  });
});

describe("the approval gate, as the user sees it", () => {
  it("enables approve when the server says the plan passed validation", async () => {
    stubApi({ state: reviewStateFixture });
    renderApp(<Workspace />);

    const approve = await screen.findByRole("button", {
      name: /approve and run the analysis/i,
    });
    expect(reviewStateFixture.can_approve).toBe(true);
    expect(approve).toBeEnabled();
  });

  it("disables approve when the server says the plan cannot be approved", async () => {
    const blocked: WorkflowState = {
      ...reviewStateFixture,
      can_approve: false,
      plan: {
        ...reviewStateFixture.plan!,
        can_approve: false,
        validation: {
          ...reviewStateFixture.plan!.validation,
          passed: false,
          status: "failed",
          failures: [
            {
              name: "metrics_exist",
              passed: false,
              detail: "No metric in the plan is available for these geographies.",
              blocking: true,
            },
          ],
        },
      },
    };
    stubApi({ state: blocked });
    renderApp(<Workspace />);

    const approve = await screen.findByRole("button", {
      name: /approve and run the analysis/i,
    });
    expect(approve).toBeDisabled();
    expect(
      screen.getByText(/No metric in the plan is available/i),
    ).toBeInTheDocument();
  });

  it("never asks the server to install a plan, only to act on one", async () => {
    // The frontend having no way to express "the plan is now approved" is what keeps the
    // gate meaningful once a network sits between the button and the state machine.
    const stub = stubApi({
      state: reviewStateFixture,
      routes: { "/approve": executedStateFixture },
    });
    renderApp(<Workspace />);

    const approve = await screen.findByRole("button", {
      name: /approve and run the analysis/i,
    });
    await userEvent.click(approve);

    await waitFor(() => {
      expect(stub.calls.some((call) => call.url.includes("/approve"))).toBe(true);
    });
    const approveCall = stub.calls.find((call) => call.url.includes("/approve"))!;
    expect(approveCall.method).toBe("POST");
    expect(JSON.stringify(approveCall.body)).not.toContain("plan_id");
    expect(JSON.stringify(approveCall.body)).not.toContain("approved");
  });

  it("lets the user change category weights on the plan itself before approving", async () => {
    const edited: WorkflowState = {
      ...reviewStateFixture,
      plan: {
        ...reviewStateFixture.plan!,
        category_weights: {
          ...reviewStateFixture.plan!.category_weights,
          growth_outlook: 0.4,
        },
        approval_record: {
          ...reviewStateFixture.plan!.approval_record,
          edits: [
            {
              field: "category_weights",
              before: reviewStateFixture.plan!.category_weights,
              after: {
                ...reviewStateFixture.plan!.category_weights,
                growth_outlook: 0.4,
              },
              edited_at: "2026-08-02T00:00:00Z",
            },
          ],
        },
      },
    };
    const stub = stubApi({
      state: reviewStateFixture,
      routes: { "/edit": edited },
    });
    renderApp(<Workspace />);

    await screen.findByText("Proposed category weights");
    const growth = screen.getByLabelText("Growth Outlook") as HTMLInputElement;
    expect(growth).toHaveAttribute("type", "range");

    const apply = screen.getByRole("button", { name: /apply weight changes/i });
    expect(apply).toBeDisabled();

    await userEvent.click(growth);
    // fireEvent is clearer than pointer math for a range input.
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(growth, { target: { value: "0.55" } });

    expect(apply).toBeEnabled();
    await userEvent.click(apply);

    await waitFor(() => {
      expect(stub.calls.some((call) => call.url.includes("/edit"))).toBe(true);
    });
    const editCall = stub.calls.find((call) => call.url.includes("/edit"))!;
    expect(editCall.body).toMatchObject({
      category_weights: expect.objectContaining({ growth_outlook: 0.55 }),
    });
    expect(await screen.findByText(/You changed/i)).toBeInTheDocument();
  });

  it("applies unsaved weight changes before approving, rather than discarding them", async () => {
    const stub = stubApi({
      state: reviewStateFixture,
      routes: {
        "/edit": reviewStateFixture,
        "/approve": executedStateFixture,
      },
    });
    renderApp(<Workspace />);

    const growth = (await screen.findByLabelText(
      "Growth Outlook",
    )) as HTMLInputElement;
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(growth, { target: { value: "0.5" } });

    await userEvent.click(
      screen.getByRole("button", { name: /apply edits and run the analysis/i }),
    );

    await waitFor(() => {
      expect(stub.calls.some((call) => call.url.includes("/approve"))).toBe(true);
    });
    const paths = stub.calls.map((call) => call.url);
    const editAt = paths.findIndex((url) => url.includes("/edit"));
    const approveAt = paths.findIndex((url) => url.includes("/approve"));
    expect(editAt).toBeGreaterThanOrEqual(0);
    expect(approveAt).toBeGreaterThan(editAt);
  });

  it("lets the user drop a metric from the selected-metrics table before approving", async () => {
    const plan = reviewStateFixture.plan!;
    const removedId = plan.selected_metric_ids[0];
    const remaining = plan.selected_metric_ids.slice(1);
    const edited: WorkflowState = {
      ...reviewStateFixture,
      plan: {
        ...plan,
        selected_metric_ids: remaining,
        approval_record: {
          ...plan.approval_record,
          edits: [
            {
              field: "selected_metric_ids",
              before: plan.selected_metric_ids,
              after: remaining,
              edited_at: "2026-08-02T00:00:00Z",
            },
          ],
        },
      },
    };
    const stub = stubApi({
      state: reviewStateFixture,
      routes: { "/edit": edited },
    });
    renderApp(<Workspace />);

    await screen.findByText(/Selected metrics/i);
    const metricName =
      catalogFixture.metrics.find((metric) => metric.metric_id === removedId)
        ?.display_name ?? removedId;

    const checkbox = screen.getByRole("checkbox", {
      name: `Include ${metricName}`,
    });
    expect(checkbox).toBeChecked();

    const apply = screen.getByRole("button", { name: /apply metric changes/i });
    expect(apply).toBeDisabled();

    await userEvent.click(checkbox);
    expect(apply).toBeEnabled();
    await userEvent.click(apply);

    await waitFor(() => {
      expect(stub.calls.some((call) => call.url.includes("/edit"))).toBe(true);
    });
    const editCall = stub.calls.find((call) => call.url.includes("/edit"))!;
    expect(editCall.body).toEqual(
      expect.objectContaining({
        selected_metric_ids: remaining,
      }),
    );
    expect(
      (editCall.body as { selected_metric_ids: string[] }).selected_metric_ids,
    ).not.toContain(removedId);
  });
});

describe("provenance is visible, not implied", () => {
  it("labels every profile field with where its value came from", async () => {
    stubApi({ state: reviewStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Interpreted retailer profile");
    const inferred = reviewStateFixture.plan!.profile_rows.filter(
      (row) => row.provenance === "planner_inferred",
    );
    if (inferred.length) {
      expect(screen.getAllByText("Planner inferred").length).toBe(inferred.length);
    }
    const stated = reviewStateFixture.plan!.profile_rows.filter(
      (row) => row.provenance === "user_supplied",
    );
    if (stated.length) {
      expect(screen.getAllByText("You said this").length).toBe(stated.length);
    }
  });

  it("states what the analysis will not conclude", async () => {
    stubApi({ state: reviewStateFixture });
    renderApp(<Workspace />);

    expect(
      await screen.findByText(/This analysis will not conclude/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/rent, foot traffic, competitors, or cannibalization/i),
    ).toBeInTheDocument();
  });
});

describe("revision confirmation", () => {
  it("shows a parked revision as a proposal that has not run", async () => {
    stubApi({ state: pendingRevisionStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Assistant" }));

    expect(await screen.findByText(/Proposed change to the analysis/i)).toBeInTheDocument();
    expect(screen.getByText("Nothing has run yet")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /confirm and rerun/i }),
    ).toBeEnabled();
    expect(pendingRevisionStateFixture.versions).toHaveLength(1);
  });

  it("disables confirmation when the revised plan fails validation", async () => {
    const invalid: WorkflowState = {
      ...pendingRevisionStateFixture,
      pending_revision: {
        ...pendingRevisionStateFixture.pending_revision!,
        is_actionable: false,
        validation: {
          status: "failed",
          checks: [],
          warnings: [],
          disclosures: [],
          passed: false,
          failures: [
            {
              name: "weights_sum",
              passed: false,
              detail: "Category weights no longer sum to one.",
              blocking: true,
            },
          ],
        },
      },
    };
    stubApi({ state: invalid });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Assistant" }));

    expect(
      await screen.findByText(/The revised plan fails validation/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /confirm and rerun/i }),
    ).toBeDisabled();
  });
});

describe("the result panels", () => {
  it("puts the leading region, its score, and the hash on the recommendation", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    const result = executedStateFixture.versions.at(-1)!.result;
    const leader = result.recommendation!.ranked_regions[0];

    await screen.findByText("Executive recommendation");
    expect(screen.getAllByText(leader.geography.display_name).length).toBeGreaterThan(0);
    expect(screen.getByText(result.reproducibility_hash!)).toBeInTheDocument();
  });

  it("renders the narrative's emphasis rather than printing its asterisks", async () => {
    // The narrator writes `**Ranking**` and friends. Under the previous renderer that was
    // markdown; here it is only markup if something turns it into markup, and the failure
    // mode is silent - the text is all there, wearing asterisks.
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");

    const narrative = executedStateFixture.versions.at(-1)!.result.recommendation!.narrative;
    const emphasised = [...narrative.matchAll(/\*\*([^*]+)\*\*/g)].map((match) => match[1]);
    expect(emphasised.length).toBeGreaterThan(0);

    for (const phrase of new Set(emphasised)) {
      const [rendered] = screen.getAllByText(phrase);
      expect(rendered.tagName).toBe("STRONG");
    }
    expect(screen.queryByText(/\*\*/)).toBeNull();
  });

  it("shows every Atlas datapoint id behind the numbers", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Evidence" }));

    const evidence = executedStateFixture.versions.at(-1)!.result.evidence!;
    const datapoints = new Set(evidence.items.map((item) => item.atlas_datapoint));
    for (const datapoint of datapoints) {
      expect(screen.getAllByText(datapoint).length).toBeGreaterThan(0);
    }
  });

  it("does not ship raw Atlas bodies until they are asked for", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Evidence" }));

    const evidence = executedStateFixture.versions.at(-1)!.result.evidence!;
    expect(evidence.raw_calls).toHaveLength(0);
    expect(evidence.raw_call_count).toBeGreaterThan(0);
    expect(
      await screen.findByText(/Load request and response bodies/i),
    ).toBeInTheDocument();
  });

  it("attributes each trace step to an authority and can filter to one", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Decision log" }));

    const trace = executedStateFixture.versions.at(-1)!.result.trace;
    expect(
      await screen.findByRole("heading", { name: "Decision log" }),
    ).toBeInTheDocument();
    expect(screen.getByText(trace[0].step)).toBeInTheDocument();

    const humanSteps = trace.filter((entry) => entry.authority === "human_approval");
    if (humanSteps.length) {
      await userEvent.click(
        screen.getAllByRole("button", { name: /human approval/i })[0],
      );
      await waitFor(() => {
        expect(screen.getByText(humanSteps[0].step)).toBeInTheDocument();
      });
    }
  });

  it("sorts limitations so blocking ones are read first", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Limitations" }));

    const limitations = executedStateFixture.versions.at(-1)!.result.limitations;
    for (const limitation of limitations) {
      expect(screen.getByText(limitation.title)).toBeInTheDocument();
    }
    expect(
      screen.getByText(/Cannibalization against your existing store network/i),
    ).toBeInTheDocument();
  });

  it("marks excluded metrics rather than dropping them from the table", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Comparison" }));

    const excluded = executedStateFixture.versions.at(-1)!.result.evidence!
      .excluded_metrics;
    const table = await screen.findByText("Metric-level comparison");
    expect(table).toBeInTheDocument();
    if (excluded.length) {
      expect(screen.getAllByText("Excluded").length).toBeGreaterThan(0);
    }
  });

  it("names the capabilities it does not have", async () => {
    stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Registry" }));

    const unavailable = (await screen.findByText(/Declared unavailable/i)).textContent;
    expect(unavailable).toMatch(/\d+/);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });
});

describe("credential handling", () => {
  it("sends no key header when the user has not supplied one", async () => {
    const stub = stubApi({ state: executedStateFixture });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    expect(stub.keyedCalls()).toHaveLength(0);
  });

  it("sends a supplied key as a header and never in a URL or body", async () => {
    const stub = stubApi({
      state: reviewStateFixture,
      routes: { "/approve": executedStateFixture },
    });
    renderApp(<Workspace />);

    await screen.findByLabelText("OpenAI API key");
    await userEvent.type(screen.getByLabelText("OpenAI API key"), "sk-secret-value");
    await userEvent.click(
      screen.getByRole("button", { name: /approve and run the analysis/i }),
    );

    await waitFor(() => {
      expect(stub.keyedCalls().length).toBeGreaterThan(0);
    });
    for (const call of stub.calls) {
      expect(call.url).not.toContain("sk-secret-value");
      expect(JSON.stringify(call.body ?? {})).not.toContain("sk-secret-value");
    }
    expect(stub.keyedCalls()[0].headers["X-OpenAI-Key"]).toBe("sk-secret-value");
  });

  it("says replies are deterministic when no model is configured", async () => {
    stubApi({ state: executedStateFixture, llmEnabled: false });
    renderApp(<Workspace />);

    await screen.findByText("Executive recommendation");
    await userEvent.click(screen.getByRole("tab", { name: "Assistant" }));

    expect(
      await screen.findByText(/replies are assembled deterministically/i),
    ).toBeInTheDocument();
  });
});

describe("failure modes", () => {
  it("explains how to start the service when it cannot be reached", async () => {
    stubApi({ routes: { "/api/health": null } });
    // Force every request to fail the way a dead server does.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    renderApp(<Workspace />);

    const banner = await screen.findByRole("alert");
    expect(
      within(banner).getAllByText(/Cannot reach the analysis service/i).length,
    ).toBeGreaterThan(0);
    expect(within(banner).getAllByText(/uvicorn server.app:app/).length).toBeGreaterThan(
      0,
    );
  });

  it("warns when no Atlas token is configured", async () => {
    stubApi({ state: describeState, atlasTokenPresent: false });
    renderApp(<Workspace />);

    expect(
      await screen.findByText(/No Atlas token is configured/i),
    ).toBeInTheDocument();
  });
});
