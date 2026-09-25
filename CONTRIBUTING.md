# Contributing

Keep Agent Queue small, local and honest about what it knows. An inferred terminal state is not an authoritative agent event; accepting text in iTerm2 is not completing the request.

## Setup

Use Python 3.12+ and Node 22.12+ (24 recommended).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix dashboard ci
.venv/bin/python -m pytest tests -q
npm --prefix dashboard run lint
npm --prefix dashboard run build
cd dashboard
npx playwright install chromium
npm run test:e2e
```

Live monitor dependencies are in `monitor/requirements.txt`. They are optional for tests and the demo. Live manual testing requires iTerm2 on macOS; CI stays cross-platform.

## Where to make changes

| Area | Files |
| --- | --- |
| Detection and terminal handling | `monitor/patterns.py`, `monitor/commands.py`, `monitor/claude_monitor.py` |
| Wire validation and persistence | `server/models.py`, `server/state.py` |
| Delivery and connections | `server/main.py` |
| Inbox UI and connection adapter | `dashboard/src/components/Inbox.tsx`, `dashboard/src/hooks/useWebSocket.ts` |
| Isolated simulation | `dashboard/src/demo.ts` |
| Browser behavior | `dashboard/e2e/` |

Add a regression before changing a delivery boundary. Include disconnect, changed-screen and duplicate/late-message cases where applicable. Never introduce automatic command replay or permission approval based on terminal text.

## Review checklist

- Tests exercise behavior, including failure outcomes.
- UI text says whether content is simulated, captured, unavailable, or delivered.
- No secrets, real terminal captures, state snapshots or machine-specific paths enter Git.
- Setup works without a global Python package install or Bun.
- Accessibility includes native controls, keyboard focus, readable status labels and small-screen layout.
- Documentation states the actual scope and limitations.

## Reproduce media

Start `npm run demo` from `dashboard/`. In a second terminal in that directory, run `npm run capture`. Chromium must already be installed with Playwright. The capture script writes screenshots and a WebM walkthrough to `docs/media/`. All media must come from the real UI with its demo label visible.
