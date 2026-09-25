import { useCallback, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { Inbox } from "./components/Inbox";
import { DEMO, demoSessions, simulateCommand } from "./demo";
import type { SessionState, Command, ServerMessage } from "./types";

export default function App() {
  const [sessions, setSessions] = useState<Record<string, SessionState>>(() =>
    DEMO ? demoSessions() : {},
  );
  const [selectedId, setSelectedId] = useState<string | null>(
    DEMO ? "retry-policy" : null,
  );
  const [monitorConnected, setMonitorConnected] = useState(false);
  const [resetKey, setResetKey] = useState(0);
  const handleMessage = useCallback((message: ServerMessage) => {
    if (message.type === "snapshot") {
      setSessions(message.sessions);
      setMonitorConnected(message.monitor_connected);
    } else if (message.type === "event") {
      setSessions((previous) => ({
        ...previous,
        [message.session.session_id]: message.session,
      }));
      if (
        message.queue_item &&
        typeof Notification !== "undefined" &&
        Notification.permission === "granted"
      ) {
        new Notification(`Agent Queue · ${message.session.tab_name}`, {
          body: message.session.status.replaceAll("_", " "),
        });
      }
    }
  }, []);
  const { connected, sendCommand } = useWebSocket(handleMessage, !DEMO);
  const handleCommand = useCallback(
    async (command: Command) => {
      if (!DEMO) return sendCommand(command);
      const result = await simulateCommand(command);
      if (command.command === "send_text" || command.command === "rename_tab") {
        setSessions((previous) => {
          const session = previous[command.session_id];
          return {
            ...previous,
            [command.session_id]: {
              ...session,
              revision: session.revision + 1,
              ...(command.command === "send_text"
                ? {
                    status: "working" as const,
                    tail_output: `${session.tail_output}\n\n❯ ${command.payload.text}\n\n[Simulation] Reply received. Working on your follow-up…`,
                  }
                : { tab_name: command.payload.name }),
            },
          };
        });
      }
      return result;
    },
    [sendCommand],
  );
  function resetDemo() {
    setSessions(demoSessions());
    setSelectedId("retry-policy");
    setResetKey((key) => key + 1);
  }
  return (
    <Inbox
      key={resetKey}
      sessions={sessions}
      selected={selectedId ? (sessions[selectedId] ?? null) : null}
      connected={connected}
      monitorConnected={monitorConnected}
      demo={DEMO}
      onSelect={setSelectedId}
      onCommand={handleCommand}
      onReset={resetDemo}
    />
  );
}
