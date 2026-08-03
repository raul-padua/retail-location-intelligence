import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ExecutedStage } from "@/components/stages/ExecutedStage";
import { SelectionProvider } from "@/lib/selection";
import { executedStateFixture } from "@/test/fixtures.generated";
import { renderApp, stubApi } from "@/test/harness";

function renderExecutedStage() {
  return renderApp(
    <SelectionProvider>
      <ExecutedStage />
    </SelectionProvider>,
  );
}

describe("SimulationPanel", () => {
  it("shows simulated retailer banner and never claims real GAP data", async () => {
    stubApi({ state: executedStateFixture });
    renderExecutedStage();

    await userEvent.click(await screen.findByRole("tab", { name: "Retailer simulation" }));

    expect(await screen.findByText("Simulated retailer data")).toBeInTheDocument();
    expect(screen.getByText(/NorthStar Apparel is a fictional brand/i)).toBeInTheDocument();
    expect(screen.queryByText(/GAP data/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/real GAP/i)).not.toBeInTheDocument();
  });

  it("runs a simulation from explicit scenario inputs", async () => {
    const stub = stubApi({ state: executedStateFixture });
    renderExecutedStage();

    await userEvent.click(await screen.findByRole("tab", { name: "Retailer simulation" }));
    await screen.findByRole("button", { name: "Run simulation" });

    await userEvent.click(screen.getByRole("button", { name: "Run simulation" }));

    await waitFor(() => {
      expect(stub.calls.some((call) => call.url.includes("/retailer-simulation/run"))).toBe(
        true,
      );
    });

    expect(await screen.findByText("Reconciliation passed")).toBeInTheDocument();
    expect(screen.getAllByText("NorthStar Burlington Mall").length).toBeGreaterThan(0);
    expect(screen.getByText("Performance in similar markets")).toBeInTheDocument();
  });
});
