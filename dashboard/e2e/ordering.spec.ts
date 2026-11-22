import { test, expect, type WebSocketRoute } from "@playwright/test";

test("session ordering uses displayed names within availability and attention groups", async ({ page }) => {
  let connection: WebSocketRoute;
  const sessions = Object.fromEntries([
    { session_id: "Zulu", tab_name: "", status: "ready", available: true },
    { session_id: "Beta", tab_name: "", status: "needs_input", available: true },
    { session_id: "hidden-id", tab_name: "Alpha", status: "permission_prompt", available: true },
    { session_id: "working", tab_name: "Aardvark", status: "working", available: true },
    { session_id: "offline", tab_name: "AAA offline", status: "ready", available: false },
  ].map((session) => [session.session_id, {
    ...session, summary: "Synthetic ordering fixture", tail_output: "Captured output",
    last_event_time: 1, last_seen: 1, revision: 1,
  }]));
  const snapshot = () => connection.send(JSON.stringify({
    type: "snapshot", monitor_connected: true, queue: [], sessions,
  }));
  await page.routeWebSocket("**/ws/dashboard", (socket) => {
    connection = socket;
    snapshot();
  });
  await page.goto("/");
  const names = page.locator(".session-row .session-name");
  await expect(names).toHaveText(["Alpha", "Beta", "Zulu", "Aardvark", "AAA offline"]);

  await page.getByRole("button", { name: "Attention 3", exact: true }).click();
  await expect(names).toHaveText(["Alpha", "Beta", "Zulu"]);
  await page.locator(".session-row").filter({ hasText: "Beta" }).click();
  await expect(page.getByRole("heading", { name: "Beta", exact: true })).toBeVisible();

  // A later name observation updates both the ordering and the selected detail.
  sessions.Beta.tab_name = "Zzz renamed";
  sessions.Beta.revision++;
  snapshot();
  await expect(names).toHaveText(["Alpha", "Zulu", "Zzz renamed"]);
  await expect(page.getByRole("heading", { name: "Zzz renamed", exact: true })).toBeVisible();
  await expect(page.locator(".session-row[aria-pressed=true] .session-name")).toHaveText("Zzz renamed");
  await page.getByRole("button", { name: "All 5", exact: true }).click();
  await expect(names).toHaveText(["Alpha", "Zulu", "Zzz renamed", "Aardvark", "AAA offline"]);
});
