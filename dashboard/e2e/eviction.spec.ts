import { test, expect } from "@playwright/test";

test("live snapshot removes an evicted session without reconnecting", async ({ page }) => {
  let connections = 0;
  let sendSnapshot: (ids: string[]) => void = () => {
    throw new Error("Dashboard socket has not connected");
  };
  await page.routeWebSocket("**/ws/dashboard", (socket) => {
    connections++;
    sendSnapshot = (ids) => socket.send(JSON.stringify({
      type: "snapshot", monitor_connected: true, queue: [],
      sessions: Object.fromEntries(ids.map((id) => [id, {
        session_id: id, tab_name: `Fixture ${id}`, status: "ready",
        summary: "Synthetic eviction fixture", tail_output: "Ready",
        last_event_time: 1, last_seen: 1, available: true, revision: 1,
      }])),
    }));
    sendSnapshot(["old", "retained"]);
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Fixture old/ }).click();
  await expect(page.getByRole("heading", { name: "Fixture old" })).toBeVisible();
  sendSnapshot(["retained", "new"]);
  await expect(page.locator(".session-row")).toHaveCount(2);
  await expect(page.getByRole("button", { name: /Fixture old/ })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Fixture old" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Fixture retained/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Fixture new/ })).toBeVisible();
  expect(connections).toBe(1);
});
