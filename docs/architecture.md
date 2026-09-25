# Architecture and delivery guarantees

Agent Queue has three live components: an iTerm2 monitor, a single-process FastAPI relay, and a React inbox. The browser-only demo is a fourth, deliberately disconnected adapter.

## State and freshness

The monitor scans iTerm2 every two seconds and recognizes Claude Code from screen signatures. It sends changed events, a full observation at least every ten seconds, and an inventory of sessions successfully observed in each pass. A reconnect clears detection caches so unchanged terminals are replayed.

The relay timestamps receipt with Unix time, advances a session revision, and maintains at most 100 sessions / 500 attention items. A removed inventory entry or disconnected monitor marks sessions unavailable immediately. A background expiry task detects stale observations after 15 seconds. The UI distinguishes the dashboard connection from the monitor connection.

Snapshots contain session state, attention items, and captured output. They are written to a temporary owner-only file in the destination directory, flushed, and atomically replaced. Restoration validates the schema and marks every session unavailable. A corrupted file stops startup with a recovery message rather than silently discarding data. This is crash-resistant local storage, not a replicated database or a power-loss durability guarantee.

Why JSON instead of SQLite? The UI consumes whole bounded snapshots; there are no query workloads or multi-process writers. A versioned JSON file makes that contract inspectable. SQLite would be appropriate if history/search requirements expand.

## Command lifecycle

1. Browser generates a command ID and includes the currently displayed revision.
2. Relay validates payload, session availability, freshness, revision and allowed interaction state. It rejects a second in-flight command for the same session.
3. Monitor re-reads the target terminal. A text reply requires an exact match to captured output, a recognized Claude session an empty current Claude prompt, and iTerm2 reporting `jobName=claude` immediately before typing. A shell with old Claude output cannot satisfy this process check. Unknown foreground names fail closed.
4. Monitor sends one single-line reply followed by carriage return, or performs a focus/rename operation.
5. Only after iTerm2 accepts the call does the monitor acknowledge it.
6. Relay resolves attention and invalidates that screen revision after acknowledged text delivery. The browser displays the result.

There is no exactly-once promise. If the connection fails after typing but before acknowledgement, delivery is unknown. The relay times out after five seconds and the browser allows eight seconds. Neither queues nor replays the command. Users should inspect iTerm2 before retrying.

Replies exclude terminal control characters, tabs, newlines and escape codes. Permission prompts cannot receive replies from the dashboard: they lead to the terminal. These checks reduce accidental actions; screen parsing cannot create an atomic transaction between observing and typing.

## Protocol

- `/ws/monitor`: one active monitor; events, inventory, and command acknowledgements.
- `/ws/dashboard`: snapshots, session events, command requests and results.
- `GET /api/health`: process, monitor and persistence state.
- `GET /api/sessions`: current snapshot.
- `GET /api/sessions/{id}/history`: captured excerpt.
- `POST /api/sessions/{id}/respond`: JSON `text` and `expected_revision`; same acknowledged delivery boundary as WebSocket replies.

Commands: `send_text`, `focus_tab`, `rename_tab`, `get_history`. The last command asks the monitor to read the current excerpt; regular polling publishes it. No endpoint runs arbitrary shell commands.

The UI starts from an authoritative snapshot on every WebSocket connection, uses capped exponential reconnect delay, and never optimistically marks delivery complete. Drafts stay attached to session IDs when switching tabs. Socket cleanup cancels reconnect timers on unmount.

## Trust boundary

The backend binds to 127.0.0.1, permits loopback hosts, and rejects browser origins that differ from the request host. Local non-browser tools without Origin remain allowed. This is a single-user tool, not authenticated remote access. Output is sensitive local data; do not expose the port through an unauthenticated proxy.

## Demo isolation

`?demo=1` disables the live WebSocket hook. Synthetic fixtures and replies use local React state only; refreshing/resetting restores the examples. No monitor or API endpoint is needed. Browser tests fail if any WebSocket or API traffic occurs. The checked-in screenshots and video show this mode and are not evidence of real agent productivity.

Foreground-job semantics follow the [iTerm2 session variable reference](https://iterm2.com/documentation-variables.html). This check is independent of terminal titles and captured text. It still cannot make a process check and terminal write atomic.
