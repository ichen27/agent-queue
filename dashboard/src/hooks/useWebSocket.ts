import { useEffect, useRef, useState, useCallback } from "react";
import type { ServerMessage, Command, CommandResult } from "../types";

export function useWebSocket(
  onMessage: (msg: ServerMessage) => void,
  enabled = true,
) {
  const [connected, setConnected] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const callback = useRef(onMessage);
  const pending = useRef(new Map<string, (result: CommandResult) => void>());
  useEffect(() => {
    callback.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout>;
    const requests = pending.current;
    function connect() {
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws/dashboard`,
      );
      socket.current = ws;
      ws.onopen = () => {
        retry = 0;
        setConnected(true);
      };
      ws.onmessage = ({ data }) => {
        try {
          const message = JSON.parse(data) as ServerMessage;
          if (message.type === "command_result" && message.command_id) {
            requests.get(message.command_id)?.(message);
          }
          callback.current(message);
        } catch {
          /* Ignore malformed frames; reconnect snapshots remain authoritative. */
        }
      };
      ws.onclose = () => {
        if (disposed) return;
        setConnected(false);
        socket.current = null;
        for (const resolve of requests.values())
          resolve({
            type: "command_result",
            ok: false,
            error:
              "Connection lost. Delivery may be unknown; check iTerm2 before retrying.",
          });
        requests.clear();
        timer = setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000));
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      socket.current?.close();
      socket.current = null;
      for (const resolve of requests.values())
        resolve({
          type: "command_result",
          ok: false,
          error: "Connection closed.",
        });
      requests.clear();
    };
  }, [enabled]);

  const sendCommand = useCallback(
    (command: Command): Promise<CommandResult> => {
      const ws = socket.current;
      if (ws?.readyState !== WebSocket.OPEN)
        return Promise.resolve({
          type: "command_result",
          ok: false,
          error: "Dashboard disconnected. Nothing was sent.",
        });
      const id = crypto.randomUUID();
      return new Promise((resolve) => {
        // Never replay commands when reconnecting: terminal side effects are not idempotent.
        const timer = setTimeout(() => {
          pending.current.delete(id);
          resolve({
            type: "command_result",
            ok: false,
            error: "Delivery unknown. Check iTerm2 before retrying.",
          });
        }, 8000);
        pending.current.set(id, (result) => {
          clearTimeout(timer);
          pending.current.delete(id);
          resolve(result);
        });
        ws.send(JSON.stringify({ ...command, command_id: id }));
      });
    },
    [],
  );
  return { connected, sendCommand };
}
