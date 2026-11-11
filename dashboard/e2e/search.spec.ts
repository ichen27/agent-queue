import { test, expect } from "@playwright/test";

test("search matches the displayed fallback name and session summaries", async ({ page }) => {
  await page.routeWebSocket("**/ws/dashboard", (socket) => {
    socket.send(JSON.stringify({
      type: "snapshot", monitor_connected: true, queue: [],
      sessions: {
        "Unnamed-Session-42": {
          session_id: "Unnamed-Session-42", tab_name: "", status: "ready",
          summary: "Review timeout handling", tail_output: "Captured output",
          last_event_time: 1, last_seen: 1, available: true, revision: 1,
        },
        named: {
          session_id: "named", tab_name: "Parser workspace", status: "working",
          summary: "Build parser", tail_output: "Working",
          last_event_time: 1, last_seen: 1, available: true, revision: 1,
        },
      },
    }));
  });
  await page.goto("/");
  const rows = page.locator(".session-row");
  const search = page.getByRole("searchbox", { name: "Search sessions" });
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Unnamed-Session-42" })).toBeVisible();

  await search.fill("unnamed-session");
  await expect(rows).toHaveCount(1);
  await expect(rows).toContainText("Unnamed-Session-42");
  await rows.click();
  await expect(page.getByRole("heading", { name: "Unnamed-Session-42", exact: true })).toBeVisible();

  await search.fill("TIMEOUT");
  await expect(rows).toHaveCount(1);
  await expect(rows).toContainText("Unnamed-Session-42");
  await search.fill("parser workspace");
  await expect(rows).toHaveCount(1);
  await expect(rows).toContainText("Parser workspace");
  await search.fill("no such session");
  await expect(rows).toHaveCount(0);
  await expect(page.getByText("No matching sessions")).toBeVisible();
  await search.clear();
  await expect(rows).toHaveCount(2);
});
