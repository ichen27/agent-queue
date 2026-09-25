# Running and troubleshooting Agent Queue

## Nothing appears

Confirm that iTerm2 is running, its Python API is enabled, and the monitor was granted access. Start Claude Code in an iTerm2 tab. A terminal without recognized Claude Code signatures is intentionally ignored. The dashboard connection indicator distinguishes backend reconnection from an offline monitor.

Check `http://127.0.0.1:7890/api/health`. A healthy backend can still have an offline monitor. Monitor errors appear in the terminal that ran `scripts/start.sh`; reply contents are not logged.

## A session is unavailable

It may have closed, stopped matching the supported screen patterns, failed an observation, or lost its monitor connection. Its captured output is retained. Do not assume it completed. Reopen the terminal and wait for the monitor to observe it again.

## A reply was rejected

Read the error. Changed-screen/revision errors mean you must review the latest output. Permission prompts, active work, unavailable sessions, and nonstandard input screens require iTerm2. Replies must be single-line printable text, with a maximum of 4,000 characters. If iTerm2 reports the foreground job as `node`, a shell, or an unknown wrapper, use iTerm2 directly; the monitor cannot prove that typing is safe. Tab names are limited to 100 characters.

An unknown-delivery result means the terminal may have received it. Inspect iTerm2 before manually retrying. No background resend will occur.

## Port already in use

The launch script exits if its backend process fails. Stop the earlier Agent Queue run with Ctrl-C before restarting. Do not terminate unrelated processes just to free the port. The demo uses 7891; live backend uses 7890; Vite development uses 5173.

## Reset local history

Stop the server first. Move `.agent-queue/state.json` to a private backup, then restart. A missing file starts a clean inbox. Do not commit snapshots or terminal captures containing real project data.

A corrupted snapshot is preserved and startup fails with its path. Inspect or move the file; Agent Queue does not silently overwrite it.

## Data limits and deployment

The monitor reads the latest 200 terminal lines, bounded to 100,000 characters per event. The relay keeps 100 recent sessions and 500 queue items. The oldest records can be evicted. Snapshot write failures surface as server errors; make sure the local disk is writable.

Use one backend process. Multiple Uvicorn workers would split monitor connections and in-memory state, and they would race writing the snapshot. Keep the server on loopback; there is no remote authentication or multi-user authorization.

CI tests synthetic terminal adapters and real local WebSockets. It cannot grant iTerm2 permissions or verify every Claude Code screen version. Before relying on a new version, test one disposable session: observe ready/working, send an innocuous follow-up, focus/rename the tab, close it, then restart the backend and confirm stale state cannot receive commands.
