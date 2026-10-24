import { test, expect } from "@playwright/test";

for (const replacement of ["New draft", "Original reply", null]) {
test(`late acknowledgement respects draft edits: ${replacement ?? "unchanged"}`, async ({ page }) => {
  let acknowledge: () => void = () => { throw new Error("No pending command"); };
  let sent = 0;
  await page.routeWebSocket("**/ws/dashboard", (socket) => {
    const snapshot = (summary = "") => socket.send(JSON.stringify({
      type: "snapshot", monitor_connected: true, queue: [],
      sessions: Object.fromEntries(["first", "second"].map((id) => [id, {
        session_id: id, tab_name: id, status: "ready", summary,
        tail_output: "", last_event_time: 1, last_seen: 1, available: true, revision: 1,
      }])),
    }));
    snapshot();
    socket.onMessage((raw) => {
      const command = JSON.parse(String(raw));
      sent++;
      acknowledge = () => {
        socket.send(JSON.stringify({ type: "command_result", command_id: command.command_id,
          session_id: "first", ok: true, message: "Accepted" }));
        snapshot("Acknowledgement processed");
      };
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /first/ }).click();
  const reply = page.getByRole("textbox", { name: "Reply to session" });
  await reply.fill("Original reply");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect.poll(() => sent).toBe(1);
  await page.getByRole("button", { name: /second/ }).click();
  await page.getByRole("button", { name: /first/ }).click();
  if (replacement !== null) {
    await reply.fill("");
    await reply.fill(replacement);
  }
  acknowledge();
  await expect(page.locator(".detail-summary")).toHaveText("Acknowledgement processed");
  await expect(reply).toHaveValue(replacement ?? "");
  expect(sent).toBe(1);
});

}
