/** Synthetic, in-browser examples. No network or terminal APIs are used here. */
import type {
  SessionState,
  SessionStatus,
  Command,
  CommandResult,
} from "./types";

export const DEMO = new URLSearchParams(location.search).get("demo") === "1";
export function demoSessions(): Record<string, SessionState> {
  const examples: [string, string, SessionStatus, string, string, boolean][] = [
    [
      "retry-policy",
      "payments / retry-policy",
      "ready",
      "Add bounded retries to the payment client.",
      `❯ Add bounded retries to the payment client.

I've added exponential backoff with jitter and an explicit retry budget.

CHANGES
  src/payments/client.ts       Retry transient failures only
  src/payments/retry.ts        Backoff + cancellation support
  tests/payments/retry.test.ts Deterministic clock coverage

DESIGN NOTE
  A payment request can have side effects. Every retry keeps
  the original idempotency key; validation errors never retry.

VERIFICATION · SIMULATED EXAMPLE
  ✓ Recovers after a transient 503
  ✓ Stops when the retry budget is exhausted
  ✓ Cancels immediately when the caller aborts

Ready for your review. What would you like to do next?`,
      true,
    ],
    [
      "schema-migration",
      "api / schema-migration",
      "permission_prompt",
      "Prepare the customer schema migration.",
      `I've prepared the migration and checked its rollback path.

The next step needs a decision in your terminal:

  Run the migration against the local development database?

  python manage.py migrate

Review the exact command and destination in iTerm2.
Agent Queue never approves terminal permissions for you.`,
      true,
    ],
    [
      "design-tokens",
      "web / design-tokens",
      "needs_input",
      "Consolidate the dashboard color tokens.",
      `The dashboard uses three slightly different neutral palettes.
I've mapped their current uses and found two reasonable paths.

  A. Keep the existing semantic names and normalize values.
  B. Introduce a new token layer and migrate components.

I'd use A for this release: a smaller change with fewer
unexpected visual differences.

Should I preserve the current semantic names?`,
      true,
    ],
    [
      "auth-tests",
      "api / auth-tests",
      "working",
      "Cover expired sessions and token rotation.",
      `Reading authentication middleware…
Inspecting session expiry boundaries…
Adding test cases for token rotation.

Current focus
  • Expired access token with a valid refresh token
  • Reused refresh token after rotation
  • Sign-out across multiple browser sessions

Working…`,
      true,
    ],
    [
      "docs-search",
      "docs / search-index",
      "working",
      "Index the new developer guides.",
      `Collecting guide headings…
Normalizing code-block excerpts…
Building the local search index…

Working…`,
      true,
    ],
    [
      "old-session",
      "worker / cache-refresh",
      "idle",
      "Investigate cache refresh timing.",
      `Last captured output

Cache refresh investigation paused.
This example session is no longer connected.

Its captured output stays available for reference.
Commands remain disabled until the monitor sees it again.`,
      false,
    ],
  ];
  return Object.fromEntries(
    examples.map(([id, name, status, summary, output, available], index) => [
      id,
      {
        session_id: id,
        tab_name: name,
        status,
        summary,
        tail_output: output,
        last_event_time: Date.now() / 1000 - index * 75,
        last_seen: Date.now() / 1000,
        available,
        revision: 1,
      },
    ]),
  );
}

export async function simulateCommand(
  command: Command,
): Promise<CommandResult> {
  await new Promise((resolve) => setTimeout(resolve, 400));
  return {
    type: "command_result",
    session_id: command.session_id,
    ok: true,
    message:
      command.command === "focus_tab"
        ? "Demo only: a live session would open in iTerm2."
        : "Simulated locally. No terminal was contacted.",
  };
}
