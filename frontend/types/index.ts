export interface AgentStep {
  agent: string;
  status: "pending" | "running" | "completed" | "error";
  output?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  agentSteps?: AgentStep[];
  confidenceScore?: number;
}

export interface SSEEvent {
  type:
    | "agent_start"
    | "agent_end"
    | "needs_clarification"
    | "final"
    | "error";
  agent?: string;
  output?: Record<string, unknown>;
  question?: string;
  response?: string;
  confidence_score?: number;
  thread_id?: string;
  message?: string;
}
