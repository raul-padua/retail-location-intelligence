/**
 * A real browser, driving the real client, against the real API.
 *
 * The component tests render against generated fixtures, which proves the panels agree with
 * the server's projections. They cannot prove that the two processes talk to each other -
 * CORS, the API base URL, the session cookie-less handshake, and hydration are all things
 * that only exist when both are actually running. This walks the full arc once and fails on
 * any console error, because a React error boundary swallowing a crash still renders a page.
 *
 * Not part of `npm test`; it needs both servers up. Run it before shipping:
 *
 *   ./scripts/dev.sh          # repo root, in one terminal
 *   npm run smoke             # web/, in another
 *
 * Set WEB_URL if you moved the port.
 */

import { chromium } from "playwright";

const WEB_URL = process.env.WEB_URL ?? "http://localhost:3000";
const OBJECTIVE =
  "Compare Burlington and Winooski for a suburban apparel store targeting " +
  "middle-income families. Prioritize growth and accessibility.";

const failures = [];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

page.on("console", (message) => {
  if (message.type() === "error") failures.push(message.text());
});
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));

const step = async (label, action) => {
  await action();
  console.log(`  ok  ${label}`);
};

try {
  await step("describe screen renders", async () => {
    await page.goto(WEB_URL, { waitUntil: "networkidle" });
    await page
      .getByRole("heading", { name: "Describe the decision" })
      .waitFor({ timeout: 20_000 });
  });

  await step("objective and geographies accept input", async () => {
    await page.locator("#objective").fill(OBJECTIVE);
    for (const city of ["Burlington", "Winooski"]) {
      const option = page.getByRole("checkbox", { name: new RegExp(city, "i") }).first();
      if (await option.count()) await option.check();
    }
    await page.screenshot({ path: "/tmp/rli-1-describe.png" });
  });

  await step("planner returns a plan for review", async () => {
    await page.getByRole("button", { name: /propose/i }).first().click();
    await page
      .getByRole("heading", { name: "Proposed analysis plan" })
      .waitFor({ timeout: 30_000 });
    await page.screenshot({ path: "/tmp/rli-2-review.png" });
  });

  await step("approval runs the pipeline and renders a recommendation", async () => {
    await page.getByRole("button", { name: "Approve and run the analysis" }).click();
    await page.getByRole("tab").first().waitFor({ timeout: 60_000 });
    await page.waitForTimeout(1_500);
    await page.screenshot({ path: "/tmp/rli-3-result.png" });
  });

  const tabs = await page.getByRole("tab").allTextContents();
  console.log(`  --  tabs: ${tabs.join(" · ")}`);

  for (const label of ["Sensitivity", "Evidence", "Decision log", "Assistant"]) {
    const tab = page.getByRole("tab", { name: new RegExp(label, "i") }).first();
    if (!(await tab.count())) continue;
    await step(`${label} tab renders`, async () => {
      await tab.click();
      await page.waitForTimeout(1_200);
      await page.screenshot({
        path: `/tmp/rli-4-${label.toLowerCase().replace(/\s+/g, "-")}.png`,
      });
    });
  }

  await step("a revision request produces a proposal and does not rerun", async () => {
    await page.getByRole("tab", { name: /assistant/i }).first().click();
    await page
      .getByPlaceholder(/ask about the regions/i)
      .fill("Double the importance of household income");
    await page.getByRole("button", { name: /^send$/i }).click();
    await page
      .getByText(/proposed change to the analysis/i)
      .first()
      .waitFor({ timeout: 30_000 });

    const confirm = page.getByRole("button", { name: /confirm and rerun/i }).first();
    if (!(await confirm.isVisible())) throw new Error("no confirmation step offered");
    if (await page.getByText(/Version 2/).count()) {
      throw new Error("a revision ran without confirmation");
    }
    await page.screenshot({ path: "/tmp/rli-5-revision.png" });
  });
} catch (error) {
  // A bare "locator timed out" says nothing about why. Whatever the page ended up showing
  // is the actual diagnosis, so print it before failing.
  console.error(`\nFAILED: ${error.message.split("\n")[0]}`);
  await page.screenshot({ path: "/tmp/rli-failure.png", fullPage: true });
  console.error("\nPage text at failure:\n");
  console.error((await page.locator("body").innerText().catch(() => "<no body>")).slice(0, 2_000));
  failures.push(error.message.split("\n")[0]);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(`\n${failures.length} console error(s):`);
  for (const failure of failures) console.error(`  ${failure}`);
  process.exit(1);
}

console.log("\nNo console errors. Screenshots in /tmp/rli-*.png");
