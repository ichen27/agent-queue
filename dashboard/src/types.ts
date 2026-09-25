export type SessionStatus =
  "working" | "ready" | "needs_input" | "permission_prompt" | "idle";
export interface SessionState {
  session_id: string;
  tab_name: string;
  status: SessionStatus;
  tail_output: string;
  summary: string;
  last_event_time: number;
  last_seen: number;
  available: boolean;
  revision: number;
}
export interface QueueItem {
  id: string;
  session_id: string;
  event_type: string;
  tail_output: string;
  status: "pending" | "seen" | "resolved";
  created_at: number;
}
export interface Command {
  command: "send_text" | "focus_tab" | "get_history" | "rename_tab";
  session_id: string;
  payload: Record<string, string>;
  command_id?: string;
  expected_revision?: number;
}
export interface CommandResult {
  type: "command_result";
  command_id?: string;
  session_id?: string;
  ok: boolean;
  message?: string;
  error?: string;
}
export type ServerMessage =
  | {
      type: "snapshot";
      sessions: Record<string, SessionState>;
      queue: QueueItem[];
      monitor_connected: boolean;
    }
  | { type: "event"; session: SessionState; queue_item?: QueueItem }
  | CommandResult;
