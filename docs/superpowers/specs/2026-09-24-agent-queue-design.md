# Agent Queue release design

Agent Queue is a local inbox for developers supervising Claude Code sessions in iTerm2. This release prioritizes trustworthy state and a frictionless way to understand the tool. The existing FastAPI/WebSocket/React architecture remains; there is no hosted service or account system.

## Chosen approach

Persist bounded session snapshots to an atomic local JSON file. A monitor connection reconciles the complete active session list and resends state after reconnect. Disconnected, removed, or expired sessions remain visible as unavailable; commands cannot target them. State restoration never implies the monitor is connected. Use server receipt time for freshness and Unix time for display.

Give each command a unique ID. The monitor acknowledges only after iTerm2 accepts the operation. The server waits for that acknowledgement before resolving attention. A timeout is an uncertain outcome, never an automatic retry: exactly-once terminal effects cannot be guaranteed across a dropped connection. Validate commands, require a current matching session revision for text delivery, reject control characters, and recheck terminal state in the monitor before typing. Permission decisions stay in iTerm2 because screen-text inference is insufficient for safe approval.

Use a browser-only demo adapter with synthetic sessions and simulated replies. Demo never opens a WebSocket or calls an API. The demo banner remains visible. A refined, keyboard-accessible inbox has status filtering, readable output, explicit connection state, and visible command results. No response is optimistically labeled delivered.

Alternatives considered: SQLite adds schema/migration overhead without a query requirement; ephemeral state leaves operators unable to distinguish restart from completion. Atomic bounded JSON fits a single local process. A fake backend demo could accidentally share live connections; client-only simulation creates a clearer isolation boundary.

## Boundaries

macOS/iTerm2 is required for live operation. Demo is cross-platform. Pattern detection is heuristic and the read window is 200 terminal lines, not full conversation history. The app stays bound to loopback; origin/host checks reduce browser-based cross-origin misuse but are not multi-user authentication. Terminal contents are sensitive and remain local. One backend process and one monitor are supported.

## Verification

Regression tests cover persistence, stale reconciliation, duplicate monitor rejection, command acknowledgement/failure/timeout, malformed messages, control character rejection, and origin checks. Run the complete Python suite, frontend typecheck/build/lint, and browser tests against the real demo UI. Capture screenshots from that UI, not design mockups.
