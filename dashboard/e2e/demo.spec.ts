import { test, expect } from "@playwright/test";

test("demo is isolated, searchable, and simulates a reply without terminal traffic", async ({
  page,
}) => {
  const terminalRequests: string[] = [];
  const sockets: string[] = [];
  const errors: string[] = [];
  page.on("request", (r) => {
    if (/\/api\/|\/ws\//.test(r.url())) terminalRequests.push(r.url());
  });
  page.on("websocket", (ws) => {
    sockets.push(ws.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/?demo=1");
  await expect(
    page.getByText("INTERACTIVE DEMO", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "payments / retry-policy" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Working 2", exact: true }).click();
  await expect(page.locator(".session-row")).toHaveCount(2);
  await page.getByRole("button", { name: "All 6", exact: true }).click();
  await page.getByRole("searchbox").fill("tokens");
  await expect(page.locator(".session-row")).toHaveCount(1);
  await page.locator(".session-row").click();
  await expect(
    page.getByRole("heading", { name: "web / design-tokens" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Reply to session" })
    .fill("Preserve the semantic names.");
  await page.getByRole("button", { name: "Simulate reply" }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Simulated locally. No terminal was contacted.",
  );
  await expect(page.getByLabel("Captured terminal output")).toContainText(
    "Preserve the semantic names.",
  );
  await page.getByRole("button", { name: "Reset demo" }).click();
  await expect(
    page.getByRole("heading", { name: "payments / retry-policy" }),
  ).toBeVisible();
  expect(terminalRequests).toEqual([]);
  expect(sockets).toEqual([]);
  expect(errors).toEqual([]);
});

test("permission and offline sessions cannot send replies", async ({
  page,
}) => {
  await page.goto("/?demo=1");
  await page.getByRole("button", { name: /api \/ schema-migration/ }).click();
  await expect(page.getByText("A terminal decision is waiting.")).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Reply to session" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Review in iTerm2" }).click();
  await expect(page.getByRole("status")).toContainText("Demo only");
  await page.getByRole("button", { name: "Offline 1", exact: true }).click();
  await page.locator(".session-row").click();
  await expect(
    page.getByRole("button", { name: "Open in iTerm2" }),
  ).toBeDisabled();
  await expect(
    page.getByText("This session is unavailable.", { exact: false }),
  ).toBeVisible();
});

test("mobile detail navigation, reply and keyboard focus remain usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?demo=1");
  await expect(
    page.getByRole("heading", { name: "payments / retry-policy" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "← Sessions", exact: true }).click();
  await expect(page.getByRole("searchbox")).toBeVisible();
  await page.getByRole("button", { name: /web \/ design-tokens/ }).click();
  await page
    .getByRole("textbox", { name: "Reply to session" })
    .fill("Keep the existing names.");
  await page.getByRole("textbox", { name: "Reply to session" }).press("Enter");
  await expect(page.getByRole("status")).toContainText("Simulated locally");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("rename is simulated and drafts stay attached to their session", async ({
  page,
}) => {
  await page.goto("/?demo=1");
  await page
    .getByRole("textbox", { name: "Reply to session" })
    .fill("Review this first");
  await page.getByRole("button", { name: /web \/ design-tokens/ }).click();
  await expect(
    page.getByRole("textbox", { name: "Reply to session" }),
  ).toHaveValue("");
  await page.getByRole("button", { name: /payments \/ retry-policy/ }).click();
  await expect(
    page.getByRole("textbox", { name: "Reply to session" }),
  ).toHaveValue("Review this first");
  await page.getByRole("button", { name: "Rename session" }).click();
  await page
    .getByRole("textbox", { name: "Session name" })
    .fill("payments / follow-up");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "payments / follow-up" }),
  ).toBeVisible();
});

test("live adapter preserves a rejected draft and restores a reconnect snapshot", async ({ page }) => {
  let connections = 0;
  let deliveries = 0;
  await page.routeWebSocket("**/ws/dashboard", (socket) => {
    connections++;
    socket.send(JSON.stringify({
      type: "snapshot", monitor_connected: true, queue: [],
      sessions: { live: { session_id: "live", tab_name: "Live adapter fixture", status: "ready",
        summary: "Synthetic transport fixture", tail_output: "Ready", last_event_time: 1,
        last_seen: 1, available: true, revision: connections } },
    }));
    socket.onMessage((raw) => {
      const command = JSON.parse(String(raw));
      deliveries++;
      expect(command.expected_revision).toBe(1);
      socket.send(JSON.stringify({ type: "command_result", command_id: command.command_id,
        session_id: "live", ok: false, error: "Session changed. Review its latest output before sending." }));
      setTimeout(() => socket.close({ code: 1001, reason: "Synthetic disconnect" }), 200);
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Live adapter fixture/ }).click();
  await page.getByRole("textbox", { name: "Reply to session" }).fill("Keep this draft");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByRole("status")).toContainText("Session changed");
  await expect(page.getByRole("textbox", { name: "Reply to session" })).toHaveValue("Keep this draft");
  await expect.poll(() => connections).toBeGreaterThan(1);
  await expect(page.getByRole("textbox", { name: "Reply to session" })).toHaveValue("Keep this draft");
  expect(deliveries).toBe(1);
});
