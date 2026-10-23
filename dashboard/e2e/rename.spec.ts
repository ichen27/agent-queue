import { test, expect } from "@playwright/test";

test("rename opens with the latest observed name and discards cancelled edits", async ({ page }) => {
  let updateName: (name: string) => void = () => { throw new Error("Not connected"); };
  await page.routeWebSocket("**/ws/dashboard", (socket) => {
    updateName = (name) => socket.send(JSON.stringify({
      type: "snapshot", monitor_connected: true, queue: [],
      sessions: { s: { session_id: "s", tab_name: name, status: "ready",
        summary: "", tail_output: "", last_event_time: 1, last_seen: 1,
        available: true, revision: 1 } },
    }));
    updateName("Original name");
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Original name/ }).click();
  updateName("Current name");
  await expect(page.getByRole("heading", { name: "Current name" })).toBeVisible();
  await page.getByRole("button", { name: "Rename session" }).click();
  await expect(page.getByRole("textbox", { name: "Session name" })).toHaveValue("Current name");
  await page.getByRole("textbox", { name: "Session name" }).fill("Discard this");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "Rename session" }).click();
  await expect(page.getByRole("textbox", { name: "Session name" })).toHaveValue("Current name");
});
