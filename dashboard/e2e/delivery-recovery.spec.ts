import { test, expect, type WebSocketRoute } from "@playwright/test";

for (const interruption of ["timeout", "disconnect"]) {
  test(`${interruption} preserves the draft and isolates late acknowledgements`, async ({ page }) => {
    const commands: { command_id: string; payload: { text: string } }[] = [];
    let connection: WebSocketRoute;
    let connections = 0;
    const snapshot = (summary = "") => connection.send(JSON.stringify({
      type: "snapshot", monitor_connected: true, queue: [],
      sessions: { first: {
        session_id: "first", tab_name: "first", status: "ready", summary,
        tail_output: "", last_event_time: 1, last_seen: 1, available: true, revision: 1,
      } },
    }));
    const acknowledge = (id: string) => connection.send(JSON.stringify({
      type: "command_result", command_id: id, session_id: "first",
      ok: true, message: "Accepted by iTerm2",
    }));
    await page.clock.install({ time: new Date("2026-01-01T10:00:00Z") });
    await page.routeWebSocket("**/ws/dashboard", (socket) => {
      connection = socket;
      connections++;
      snapshot();
      socket.onMessage((raw) => commands.push(JSON.parse(String(raw))));
    });
    await page.goto("/");
    await page.clock.pauseAt(new Date("2026-01-01T10:01:00Z"));
    await page.getByRole("button", { name: /first/ }).click();
    const reply = page.getByRole("textbox", { name: "Reply to session" });
    await reply.fill("Original reply");
    await page.getByRole("button", { name: "Send reply" }).click();
    await expect.poll(() => commands.length).toBe(1);

    if (interruption === "timeout") {
      await page.clock.runFor(8001);
    } else {
      connection!.close();
      await expect(page.getByText("Reconnecting…", { exact: true })).toBeVisible();
      await expect(page.locator(".command-result")).toContainText("Connection lost");
      await page.clock.runFor(1001);
      await expect.poll(() => connections).toBe(2);
    }
    await expect(page.locator(".command-result")).toContainText(/unknown/i);
    await expect(reply).toHaveValue("Original reply");
    await expect(page.getByRole("button", { name: "Send reply" })).toBeEnabled();
    expect(commands).toHaveLength(1);

    // A late acknowledgement cannot clear the preserved draft or erase uncertainty.
    acknowledge(commands[0].command_id);
    snapshot("Late acknowledgement processed");
    await expect(page.locator(".detail-summary")).toHaveText("Late acknowledgement processed");
    await expect(reply).toHaveValue("Original reply");
    await expect(page.locator(".command-result")).toContainText(/unknown/i);

    // Only an explicit new send creates another command, with a fresh identity.
    await reply.fill("New reply after checking terminal");
    await page.getByRole("button", { name: "Send reply" }).click();
    await expect.poll(() => commands.length).toBe(2);
    expect(commands[1].command_id).not.toBe(commands[0].command_id);
    expect(commands[1].payload.text).toBe("New reply after checking terminal");
    acknowledge(commands[0].command_id);
    snapshot("Old acknowledgement repeated");
    await expect(page.locator(".detail-summary")).toHaveText("Old acknowledgement repeated");
    await expect(page.getByRole("button", { name: "Sending…" })).toBeDisabled();
    await expect(reply).toHaveValue("New reply after checking terminal");

    acknowledge(commands[1].command_id);
    await expect(page.locator(".command-result")).toHaveText("Accepted by iTerm2");
    await expect(reply).toHaveValue("");
    expect(commands).toHaveLength(2);
  });
}
