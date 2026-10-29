import { test, expect } from "@playwright/test";

for (const action of ["reply", "rename"]) {
  test(`reset ignores a pending simulated ${action} and accepts new commands`, async ({ page }) => {
    await page.clock.install({ time: new Date("2026-01-01T10:00:00Z") });
    await page.goto("/?demo=1");
    await page.clock.pauseAt(new Date("2026-01-01T10:01:00Z"));
    const output = page.getByLabel("Captured terminal output");
    const originalOutput = await output.textContent();

    async function submit(value: string) {
      if (action === "reply") {
        await page.getByRole("textbox", { name: "Reply to session" }).fill(value);
        await page.getByRole("button", { name: "Simulate reply" }).click();
      } else {
        await page.getByRole("button", { name: "Rename session" }).click();
        await page.getByRole("textbox", { name: "Session name" }).fill(value);
        await page.getByRole("button", { name: "Save", exact: true }).click();
      }
    }

    await submit("Discard this pending change");
    await expect(page.getByRole("button", { name: "Open in iTerm2" })).toBeDisabled();
    await page.getByRole("button", { name: "Reset demo" }).click();
    await page.clock.runFor(1000);

    await expect(page.getByRole("heading", { name: "payments / retry-policy", exact: true })).toBeVisible();
    await expect(output).toHaveText(originalOutput!);
    await expect(page.getByRole("textbox", { name: "Reply to session" })).toHaveValue("");
    await expect(page.locator(".command-result")).toHaveCount(0);

    await submit("Keep the new change");
    await page.clock.runFor(1000);
    await expect(page.getByRole("status")).toContainText("Simulated locally");
    if (action === "reply") {
      await expect(output).toContainText("Keep the new change");
    } else {
      await expect(page.getByRole("heading", { name: "Keep the new change", exact: true })).toBeVisible();
    }
  });
}
