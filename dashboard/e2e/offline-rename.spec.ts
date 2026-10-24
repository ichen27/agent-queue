import { test, expect } from "@playwright/test";

test("open rename form disables actions when the monitor goes offline", async ({ page }) => {
  let disconnectMonitor: () => void = () => { throw new Error("Not connected"); };
  let commands = 0;
  await page.routeWebSocket("**/ws/dashboard", (socket) => {
    const snapshot = (online: boolean) => socket.send(JSON.stringify({
      type: "snapshot", monitor_connected: online, queue: [],
      sessions: { s: { session_id: "s", tab_name: "Rename fixture", status: "ready",
        summary: "", tail_output: "", last_event_time: 1, last_seen: 1,
        available: true, revision: 1 } },
    }));
    snapshot(true);
    disconnectMonitor = () => snapshot(false);
    socket.onMessage(() => { commands++; });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Rename fixture/ }).click();
  await page.getByRole("button", { name: "Rename session" }).click();
  await page.getByRole("textbox", { name: "Session name" }).fill("Draft name");
  disconnectMonitor();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await expect(page.getByRole("textbox", { name: "Session name" })).toBeDisabled();
  await page.locator(".rename-form").dispatchEvent("submit");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator(".rename-form")).toHaveCount(0);
  expect(commands).toBe(0);
});
