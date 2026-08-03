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

describe("AnalogsPanel", () => {
  it("shows simulated performance banner and never claims real GAP data", async () => {
    stubApi({ state: executedStateFixture });
    renderExecutedStage();

    await userEvent.click(await screen.findByRole("tab", { name: "Analog stores" }));

    expect(await screen.findByText("What this answers")).toBeInTheDocument();
    expect(await screen.findByText("Simulated performance labels")).toBeInTheDocument();
    expect(
      screen.getByText(/NorthStar Apparel simulated data for the demo/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/GAP data/i)).not.toBeInTheDocument();
  });

  it("runs an analog search for the selected market", async () => {
    const stub = stubApi({ state: executedStateFixture });
    renderExecutedStage();

    await userEvent.click(await screen.findByRole("tab", { name: "Analog stores" }));
    await screen.findByRole("button", { name: "Find look-alike stores" });

    await userEvent.click(screen.getByRole("button", { name: "Find look-alike stores" }));

    await waitFor(() => {
      expect(stub.calls.some((call) => call.url.includes("/analog-matching/search"))).toBe(
        true,
      );
    });

    expect(await screen.findByText("NorthStar Burlington Mall")).toBeInTheDocument();
    expect(screen.getByText(/Analogy strong/i)).toBeInTheDocument();
  });
});
