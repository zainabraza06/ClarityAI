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
  sources?: string[];
  template?: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  threadId: string;
  template: string;
  createdAt: string;
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
  sources?: string[];
  thread_id?: string;
  message?: string;
}

export type TemplateId =
  | "standard"
  | "investor_memo"
  | "competitor_analysis"
  | "swot"
  | "comparison";

export interface TemplateOption {
  id: TemplateId;
  label: string;
  placeholder: string;
}

export interface StoredDocument {
  id: string;
  filename: string;
  source_type: "pdf" | "txt" | "url";
  chunk_count: number;
  uploaded_at: string;
}

export const TEMPLATES: TemplateOption[] = [
  {
    id: "standard",
    label: "Standard",
    placeholder: "Ask about any company — e.g. 'Research NVIDIA's AI strategy'",
  },
  {
    id: "investor_memo",
    label: "Investor Memo",
    placeholder: "e.g. 'Analyse OpenAI as an investment opportunity'",
  },
  {
    id: "competitor_analysis",
    label: "Competitor Analysis",
    placeholder: "e.g. 'Competitive analysis of Tesla in the EV market'",
  },
  {
    id: "swot",
    label: "SWOT",
    placeholder: "e.g. 'SWOT analysis of Apple Inc.'",
  },
  {
    id: "comparison",
    label: "Comparison",
    placeholder: "e.g. 'Compare Tesla vs Rivian: strategy and financials'",
  },
];
