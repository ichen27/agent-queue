# Agent Queue implementation plan

Execution is autonomous under the user-authorized release scope.

1. Reliability: add regression tests in tests/test_reliability.py; implement validated models, atomic bounded storage, freshness reconciliation and acknowledged command delivery in server/. Fix monitor reconnect replay and state timestamps, extract testable terminal command handling. Verify all Python tests and repair baseline detector regressions without broadening live shell recognition.
2. Experience: implement a browser-only adapter and synthetic fixtures in dashboard/src/demo.ts, reliable WebSocket hook and accessible inbox. Surface delivery outcomes, stale states, connection health and explicit demo labeling. Add browser smoke tests for filters, simulation, responsive layout and zero demo network effects. Run build and lint.
3. Release: provide explicit setup/run commands, architecture and limitations, contributor workflow, MIT license and CI. Capture desktop/mobile screenshots and demo video from the running demo with Playwright. Review diffs and commit compact, truthful changes. Do not publish or alter live services.

Baseline: commit 34a2e83; clean main; Python suite 23 passed / 4 failed before edits (three detector expectations and missing extract_tail). Existing runtime is Python 3.14; CI will also test Python 3.12.
