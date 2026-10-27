import { test, expect } from "@playwright/test";

for (const ok of [true, false]) {
  test(`command status survives session switches: ${ok ? "accepted" : "failed"}`, async ({ page }) => {
    let finish = () => { throw new Error("No pending command"); };
    let sent = 0;
    await page.routeWebSocket("**/ws/dashboard", (socket) => {
      socket.send(JSON.stringify({
        type: "snapshot", monitor_connected: true, queue: [],
        sessions: Object.fromEntries(["first", "second"].map((id) => [id, {
          session_id: id, tab_name: id, status: "ready", summary: "",
          tail_output: "", last_event_time: 1, last_seen: 1, available: true, revision: 1,
        }])),
      }));
      socket.onMessage((raw) => {
        const command = JSON.parse(String(raw));
        sent++;
        finish = () => socket.send(JSON.stringify({
          type: "command_result", command_id: command.command_id,
          session_id: "first", ok,
          message: "Accepted by iTerm2",
          error: "Delivery unknown. Check iTerm2 before retrying.",
        }));
      });
    });
    await page.goto("/");
    await page.getByRole("button", { name: /first/ }).click();
    await page.getByRole("textbox", { name: "Reply to session" }).fill("Original reply");
    await page.getByRole("button", { name: "Send reply" }).click();
    await expect.poll(() => sent).toBe(1);
    await page.getByRole("button", { name: /second/ }).click();
    await expect(page.getByRole("textbox", { name: "Reply to session" })).toBeEnabled();
    await page.getByRole("button", { name: /first/ }).click();
    await expect(page.getByRole("button", { name: "Sending…" })).toBeDisabled();

    await page.getByRole("button", { name: /second/ }).click();
    finish();
    await page.getByRole("button", { name: /first/ }).click();
    await expect(page.locator(".command-result")).toHaveText(
      ok ? "Accepted by iTerm2" : "Delivery unknown. Check iTerm2 before retrying.",
    );
    await expect(page.getByRole("textbox", { name: "Reply to session" })).toHaveValue(
      ok ? "" : "Original reply",
    );
    await page.getByRole("button", { name: /second/ }).click();
    await expect(page.locator(".command-result")).toHaveCount(0);
    expect(sent).toBe(1);
  });
}
