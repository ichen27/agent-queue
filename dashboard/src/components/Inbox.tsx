import { useState, type FormEvent } from "react";
import type { SessionState, Command, CommandResult } from "../types";

interface Props {
  sessions: Record<string, SessionState>;
  selected: SessionState | null;
  connected: boolean;
  monitorConnected: boolean;
  demo: boolean;
  onSelect: (id: string | null) => void;
  onCommand: (command: Command) => Promise<CommandResult>;
  onReset: () => void;
}
const LABELS = {
  permission_prompt: "Permission",
  needs_input: "Needs input",
  ready: "Ready for review",
  working: "Working",
  idle: "Idle",
};
const needsAttention = (s: SessionState) =>
  s.available &&
  ["ready", "needs_input", "permission_prompt"].includes(s.status);
type Filter = "all" | "attention" | "working" | "unavailable";

function Status({ session }: { session: SessionState }) {
  return (
    <span
      className={`status status-${session.available ? session.status : "unavailable"}`}
    >
      <i />
      {session.available ? LABELS[session.status] : "Unavailable"}
    </span>
  );
}

export function Inbox({
  sessions,
  selected,
  connected,
  monitorConnected,
  demo,
  onSelect,
  onCommand,
  onReset,
}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [notifications, setNotifications] = useState("");
  const all = Object.values(sessions);
  const attention = all.filter(needsAttention).length;
  const working = all.filter(
    (s) => s.available && s.status === "working",
  ).length;
  const unavailable = all.filter((s) => !s.available).length;
  const filtered = all
    .filter(
      (s) =>
        filter === "all" ||
        (filter === "attention" && needsAttention(s)) ||
        (filter === "working" && s.available && s.status === "working") ||
        (filter === "unavailable" && !s.available),
    )
    .filter((s) =>
      `${s.tab_name} ${s.summary}`.toLowerCase().includes(search.toLowerCase()),
    )
    .sort(
      (a, b) =>
        Number(b.available) - Number(a.available) ||
        Number(needsAttention(b)) - Number(needsAttention(a)) ||
        a.tab_name.localeCompare(b.tab_name),
    );
  const live = demo || (connected && monitorConnected);
  async function enableNotifications() {
    if (typeof Notification === "undefined") {
      setNotifications("This browser does not support notifications.");
      return;
    }
    const permission = await Notification.requestPermission();
    setNotifications(
      permission === "granted"
        ? "Notifications enabled."
        : "Notifications are off. You can change this in browser settings.",
    );
  }
  return (
    <div className="app-shell">
      <header className="topbar">
        <a
          className="brand"
          href={demo ? "?demo=1" : "/"}
          aria-label="Agent Queue home"
        >
          <span className="brand-icon" aria-hidden="true">
            ≋
          </span>
          Agent Queue<span className="brand-tag">LOCAL WORKSPACE</span>
        </a>
        <div className="top-actions">
          {demo ? (
            <span className="demo-chip">INTERACTIVE DEMO</span>
          ) : (
            <span className={`connection ${live ? "online" : ""}`}>
              <i />
              {!connected
                ? "Reconnecting…"
                : monitorConnected
                  ? "Monitor connected"
                  : "Monitor offline"}
            </span>
          )}
          <a
            href="https://github.com/ichen27/agent-queue"
            target="_blank"
            rel="noreferrer"
          >
            GitHub ↗
          </a>
        </div>
      </header>
      {demo && (
        <div className="demo-banner">
          <span>
            <strong>Explore a simulated workspace.</strong> Sample output and
            replies stay in this browser. No real terminals are connected.
          </span>
          <button onClick={onReset}>Reset demo ↺</button>
        </div>
      )}
      <main>
        <section className="workspace-heading">
          <div>
            <p className="eyebrow">CLAUDE CODE + ITERM2</p>
            <h1>
              Session inbox<span>.</span>
            </h1>
            <p className="subtitle">A clear view of what needs you next.</p>
          </div>
          <div className="metrics" aria-label="Session summary">
            <div>
              <span className="metric-number attention-number">
                {attention.toString().padStart(2, "0")}
              </span>
              <span>Need attention</span>
            </div>
            <div>
              <span className="metric-number">
                {working.toString().padStart(2, "0")}
              </span>
              <span>Working</span>
            </div>
            <div>
              <span className="metric-number muted-number">
                {all.length.toString().padStart(2, "0")}
              </span>
              <span>Total sessions</span>
            </div>
          </div>
        </section>
        {!demo && !live && (
          <div className="connection-notice" role="status">
            {connected
              ? "The dashboard is connected, but the iTerm2 monitor is offline. Captured output stays visible; terminal actions are disabled."
              : "Reconnecting to the local server. Commands are disabled and will not be replayed."}
          </div>
        )}
        <div className={`inbox-layout ${selected ? "has-selection" : ""}`}>
          <aside className="inbox-sidebar" aria-label="Sessions">
            <div className="sidebar-heading">
              <h2>
                Sessions <span>{all.length}</span>
              </h2>
              <span className="local-label">
                {demo ? "SAMPLE WORKSPACE" : "ON THIS MACHINE"}
              </span>
            </div>
            <div className="search-wrap">
              <span aria-hidden="true">⌕</span>
              <input
                type="search"
                aria-label="Search sessions"
                placeholder="Find a session…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="filters" aria-label="Filter sessions">
              {(
                [
                  ["all", "All", all.length],
                  ["attention", "Attention", attention],
                  ["working", "Working", working],
                  ["unavailable", "Offline", unavailable],
                ] as const
              ).map(([value, label, count]) => (
                <button
                  key={value}
                  aria-label={`${label} ${count}`}
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {label}
                  <span>{count}</span>
                </button>
              ))}
            </div>
            <div className="inbox-list">
              {filtered.map((s) => (
                <button
                  key={s.session_id}
                  className={`session-row ${selected?.session_id === s.session_id ? "selected" : ""}`}
                  aria-pressed={selected?.session_id === s.session_id}
                  onClick={() => onSelect(s.session_id)}
                >
                  <div className="session-row-top">
                    <span className="session-name">
                      {s.tab_name || s.session_id}
                    </span>
                    <span className="row-arrow" aria-hidden="true">
                      ↗
                    </span>
                  </div>
                  <p>{s.summary || "Waiting for captured output"}</p>
                  <Status session={s} />
                </button>
              ))}
              {filtered.length === 0 && (
                <div className="empty-list">
                  <strong>
                    {all.length
                      ? "No matching sessions"
                      : "Your inbox is ready"}
                  </strong>
                  <p>
                    {all.length
                      ? "Try a different search or filter."
                      : "Start the monitor and a Claude Code session in iTerm2. Your sessions will appear here."}
                  </p>
                  {!all.length && <a href="?demo=1">Explore the demo →</a>}
                </div>
              )}
            </div>
            <div className="sidebar-footer">
              <span className={`connection ${live ? "online" : ""}`}>
                <i />
                {demo
                  ? "Simulation · browser only"
                  : live
                    ? "Local monitor connected"
                    : "Waiting for connection"}
              </span>
              <span>Output stays on your machine</span>
            </div>
          </aside>
          <section className="inbox-detail" aria-label="Selected session">
            {selected ? (
              <DetailPane
                key={selected.session_id}
                session={selected}
                live={live}
                demo={demo}
                onCommand={onCommand}
                onBack={() => onSelect(null)}
                reply={drafts[selected.session_id] ?? ""}
                onReply={(text) =>
                  setDrafts((current) => ({
                    ...current,
                    [selected.session_id]: text,
                  }))
                }
              />
            ) : (
              <div className="detail-empty">
                <div className="empty-symbol" aria-hidden="true">
                  ≋
                </div>
                <h2>
                  Less tab switching.
                  <br />
                  More forward motion.
                </h2>
                <p>
                  Select a session to review its output
                  <br />
                  and decide what happens next.
                </p>
              </div>
            )}
          </section>
        </div>
        <footer className="workspace-footer">
          <span>Built for the space between agent turns.</span>
          <div>
            {notifications && <span role="status">{notifications}</span>}
            {!demo && (
              <button onClick={enableNotifications}>
                Enable notifications
              </button>
            )}
            <span>Single machine. No cloud account.</span>
          </div>
        </footer>
      </main>
    </div>
  );
}

function DetailPane({
  session,
  live,
  demo,
  onCommand,
  onBack,
  reply,
  onReply,
}: {
  session: SessionState;
  live: boolean;
  demo: boolean;
  onCommand: Props["onCommand"];
  onBack: () => void;
  reply: string;
  onReply: (text: string) => void;
}) {
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pending, setPending] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(session.tab_name);
  const available = live && session.available;
  const canReply =
    available && ["ready", "needs_input"].includes(session.status);
  async function command(
    kind: Command["command"],
    payload: Record<string, string>,
  ) {
    setPending(true);
    setResult(null);
    const outcome = await onCommand({
      command: kind,
      session_id: session.session_id,
      expected_revision: session.revision,
      payload,
    });
    setResult(outcome);
    setPending(false);
    if (outcome.ok && kind === "send_text") onReply("");
    if (outcome.ok && kind === "rename_tab") setRenaming(false);
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    if (canReply && reply.trim() && !pending)
      void command("send_text", { text: reply });
  }
  return (
    <div className="detail-pane">
      <div className="detail-header">
        <button className="back-button" onClick={onBack}>
          ← Sessions
        </button>
        <div className="detail-kicker">
          <span>SESSION DETAIL</span>
          <Status session={session} />
        </div>
        <div className="detail-title-row">
          <h2>{session.tab_name || session.session_id}</h2>
          <button
            className="icon-button"
            title="Rename session"
            aria-label="Rename session"
            disabled={!available || pending}
            onClick={() => setRenaming(!renaming)}
          >
            ✎
          </button>
        </div>
        {renaming && (
          <form
            className="rename-form"
            onSubmit={(e) => {
              e.preventDefault();
              void command("rename_tab", { name });
            }}
          >
            <input
              aria-label="Session name"
              value={name}
              maxLength={100}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
            <button disabled={pending || !name.trim()}>Save</button>
            <button type="button" onClick={() => setRenaming(false)}>
              Cancel
            </button>
          </form>
        )}
        <p className="detail-summary">
          {session.summary || "No prompt captured yet."}
        </p>
      </div>
      <div className="output-toolbar">
        <span>
          <i className="terminal-icon" aria-hidden="true">
            ›_
          </i>{" "}
          Captured output {demo && <small>SIMULATED</small>}
        </span>
        <button
          disabled={!available || pending}
          onClick={() => void command("focus_tab", {})}
        >
          Open in iTerm2 ↗
        </button>
      </div>
      <pre
        className="detail-output"
        tabIndex={0}
        aria-label="Captured terminal output"
      >
        {session.tail_output || "No output captured yet."}
      </pre>
      <div className="detail-footer">
        {result && (
          <p
            className={`command-result ${result.ok ? "success" : "failure"}`}
            role="status"
          >
            {result.ok ? result.message : result.error}
          </p>
        )}
        {session.status === "permission_prompt" && available && (
          <div className="permission-note">
            <strong>A terminal decision is waiting.</strong>
            <p>Review the exact command in iTerm2 before approving it.</p>
            <button
              className="primary-button"
              disabled={pending}
              onClick={() => void command("focus_tab", {})}
            >
              Review in iTerm2 ↗
            </button>
          </div>
        )}
        {!available && (
          <p className="unavailable-note">
            This session is unavailable. Captured output is preserved; replies
            are disabled.
          </p>
        )}
        {canReply && (
          <form onSubmit={submit}>
            <label htmlFor="reply">
              {demo ? "Try a simulated follow-up" : "Send a follow-up"}
            </label>
            <div className="reply-box">
              <input
                id="reply"
                aria-label="Reply to session"
                value={reply}
                maxLength={4000}
                onChange={(e) => onReply(e.target.value)}
                placeholder="e.g. Add a test for the timeout case"
                autoComplete="off"
                disabled={pending}
              />
              <button
                className="primary-button"
                disabled={pending || !reply.trim()}
              >
                {pending
                  ? "Sending…"
                  : demo
                    ? "Simulate reply ↑"
                    : "Send reply ↑"}
              </button>
            </div>
            <p className="reply-hint">
              {demo
                ? "Runs only in your browser. Reset the demo to start again."
                : "Enter to send · Single-line text · Delivery confirmed by iTerm2"}
            </p>
          </form>
        )}
        {available && session.status === "working" && (
          <p className="working-note">
            <i />
            {demo
              ? "This sample agent is working on its next step."
              : "Agent is working. Its next update will appear here."}
          </p>
        )}
        {available && session.status === "idle" && (
          <p className="unavailable-note">
            This session is idle. Open iTerm2 to begin a new turn.
          </p>
        )}
      </div>
    </div>
  );
}
