"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import {
  AgentStep,
  ChatMessage,
  Conversation,
  SSEEvent,
  TemplateId,
  TEMPLATES,
} from "@/types";
import MessageBubble from "./MessageBubble";
import AgentTimeline from "./AgentTimeline";
import Sidebar from "./Sidebar";

const STORAGE_KEY = "clarityai_conversations";
const MAX_CONVERSATIONS = 20;

const AGENT_ORDER = [
  "Clarity Agent",
  "Research Agent",
  "Validator Agent",
  "Synthesis Agent",
];

export default function ChatInterface() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [clarification, setClarification] = useState<{
    needed: boolean;
    question: string;
  }>({ needed: false, question: "" });

  const [selectedTemplate, setSelectedTemplate] = useState<TemplateId>("standard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── localStorage load ──────────────────────────────────────────────────────

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setConversations(JSON.parse(raw));
    } catch {
      // ignore malformed storage
    }
  }, []);

  // ── Auto-scroll ────────────────────────────────────────────────────────────

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveSteps, isProcessing]);

  // ── Conversation persistence ───────────────────────────────────────────────

  const saveConversation = useCallback(
    (msgs: ChatMessage[], tid: string, tmpl: TemplateId) => {
      const title =
        (msgs.find((m) => m.role === "user")?.content ?? "Conversation").slice(0, 55);

      setConversations((prev) => {
        const idx = prev.findIndex((c) => c.threadId === tid);
        let updated: Conversation[];

        if (idx >= 0) {
          updated = prev.map((c, i) =>
            i === idx ? { ...c, messages: msgs, template: tmpl } : c
          );
        } else {
          const newConv: Conversation = {
            id: tid,
            title: title.length === 55 ? title + "…" : title,
            messages: msgs,
            threadId: tid,
            template: tmpl,
            createdAt: new Date().toISOString(),
          };
          updated = [newConv, ...prev].slice(0, MAX_CONVERSATIONS);
        }

        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        return updated;
      });
    },
    []
  );

  // ── New / load conversation ────────────────────────────────────────────────

  const startNewConversation = () => {
    setMessages([]);
    setThreadId(null);
    setInput("");
    setLiveSteps([]);
    setClarification({ needed: false, question: "" });
    setSelectedTemplate("standard");
  };

  const loadConversation = (conv: Conversation) => {
    setMessages(conv.messages);
    setThreadId(conv.threadId);
    setSelectedTemplate((conv.template as TemplateId) ?? "standard");
    setSidebarOpen(false);
    setClarification({ needed: false, question: "" });
    setLiveSteps([]);
  };

  const deleteConversation = (id: string) => {
    setConversations((prev) => {
      const updated = prev.filter((c) => c.id !== id);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  };

  // ── Core send logic ────────────────────────────────────────────────────────

  const sendMessage = async (text: string) => {
    if (!text.trim() || isProcessing) return;

    const currentThreadId = threadId || uuidv4();
    if (!threadId) setThreadId(currentThreadId);

    setMessages((prev) => [
      ...prev,
      {
        id: uuidv4(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
        template: selectedTemplate,
      },
    ]);

    setInput("");
    setIsProcessing(true);
    setLiveSteps([]);
    setClarification({ needed: false, question: "" });

    const collectedSteps: AgentStep[] = [];

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          thread_id: currentThreadId,
          template: selectedTemplate,
        }),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;

          try {
            const event: SSEEvent = JSON.parse(raw);
            handleSSEEvent(event, collectedSteps, currentThreadId);
          } catch {
            // ignore malformed SSE lines
          }
        }
      }
    } catch {
      appendAssistantMessage(
        "Sorry, something went wrong. Please try again.",
        collectedSteps,
        undefined,
        undefined,
        currentThreadId
      );
    } finally {
      setIsProcessing(false);
      setLiveSteps([]);
    }
  };

  // ── SSE event handler ──────────────────────────────────────────────────────

  const handleSSEEvent = (
    event: SSEEvent,
    collectedSteps: AgentStep[],
    currentThreadId: string
  ) => {
    if (event.thread_id) setThreadId(event.thread_id);

    switch (event.type) {
      case "agent_start": {
        const step: AgentStep = { agent: event.agent ?? "", status: "running" };
        collectedSteps.push(step);
        setLiveSteps([...collectedSteps]);
        break;
      }

      case "agent_end": {
        const idx = findLastRunning(collectedSteps, event.agent ?? "");
        if (idx >= 0) {
          collectedSteps[idx] = {
            ...collectedSteps[idx],
            status: "completed",
            output: event.output,
          };
        }
        setLiveSteps([...collectedSteps]);
        break;
      }

      case "needs_clarification": {
        setIsProcessing(false);
        setLiveSteps([]);
        setClarification({
          needed: true,
          question: event.question ?? "Could you please clarify your query?",
        });
        break;
      }

      case "final": {
        appendAssistantMessage(
          event.response ?? "",
          [...collectedSteps],
          event.confidence_score,
          event.sources,
          event.thread_id ?? currentThreadId
        );
        break;
      }

      case "error": {
        appendAssistantMessage(
          `Research error: ${event.message}`,
          [...collectedSteps],
          undefined,
          undefined,
          currentThreadId
        );
        break;
      }
    }
  };

  const appendAssistantMessage = (
    content: string,
    steps: AgentStep[],
    confidenceScore: number | undefined,
    sources: string[] | undefined,
    tid: string
  ) => {
    setMessages((prev) => {
      const updated: ChatMessage[] = [
        ...prev,
        {
          id: uuidv4(),
          role: "assistant",
          content,
          timestamp: new Date().toISOString(),
          agentSteps: steps,
          confidenceScore,
          sources,
          template: selectedTemplate,
        },
      ];
      saveConversation(updated, tid, selectedTemplate);
      return updated;
    });
  };

  const findLastRunning = (steps: AgentStep[], agentName: string): number => {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].agent === agentName && steps[i].status === "running") return i;
    }
    return -1;
  };

  // ── Form handlers ──────────────────────────────────────────────────────────

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (clarification.needed) {
      setClarification({ needed: false, question: "" });
      sendMessage(input);
    } else {
      sendMessage(input);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const isEmpty = messages.length === 0 && !isProcessing;
  const currentTemplate = TEMPLATES.find((t) => t.id === selectedTemplate)!;

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        open={sidebarOpen}
        conversations={conversations}
        currentThreadId={threadId}
        onSelect={loadConversation}
        onDelete={deleteConversation}
        onNewChat={() => {
          startNewConversation();
          setSidebarOpen(false);
        }}
      />

      {/* Main chat column */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3 shadow-sm flex-shrink-0">
          <button
            type="button"
            onClick={() => setSidebarOpen((o) => !o)}
            className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 transition"
            title="Toggle history"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>

          <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-bold">C</span>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-slate-900">ClarityAI</h1>
            <p className="text-xs text-slate-500">Multi-agent business research</p>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {threadId && (
              <span className="text-xs text-slate-300 font-mono hidden sm:block">
                {threadId.slice(0, 8)}…
              </span>
            )}
            <button
              type="button"
              onClick={startNewConversation}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              New Chat
            </button>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto custom-scroll px-4 py-6">
          <div className="max-w-3xl mx-auto space-y-4">
            {isEmpty && (
              <WelcomeScreen
                onExampleClick={(text, tmpl) => {
                  if (tmpl) setSelectedTemplate(tmpl);
                  sendMessage(text);
                }}
              />
            )}

            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {/* Live agent progress */}
            {isProcessing && liveSteps.length > 0 && (
              <div className="flex justify-start">
                <div className="bg-white border border-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm max-w-[85%]">
                  <AgentTimeline steps={liveSteps} />
                  <div className="flex items-center gap-2 mt-1">
                    <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce" />
                    <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce [animation-delay:150ms]" />
                    <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce [animation-delay:300ms]" />
                  </div>
                </div>
              </div>
            )}

            {/* Initial spinner */}
            {isProcessing && liveSteps.length === 0 && (
              <div className="flex justify-start">
                <div className="bg-white border border-slate-100 rounded-2xl px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce" />
                    <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce [animation-delay:150ms]" />
                    <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce [animation-delay:300ms]" />
                    <span className="text-xs text-slate-400 ml-1">Thinking…</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Clarification banner */}
        {clarification.needed && (
          <div className="border-t border-amber-200 bg-amber-50 px-4 py-3 flex-shrink-0">
            <div className="max-w-3xl mx-auto">
              <p className="text-sm text-amber-800 font-medium mb-1">
                Clarification needed
              </p>
              <p className="text-sm text-amber-700">{clarification.question}</p>
            </div>
          </div>
        )}

        {/* Template selector + input */}
        <div className="bg-white border-t border-slate-200 px-4 pt-3 pb-4 flex-shrink-0">
          <div className="max-w-3xl mx-auto">
            {/* Template pills — hidden during clarification */}
            {!clarification.needed && (
              <div className="flex items-center gap-1.5 flex-wrap mb-2">
                <span className="text-xs text-slate-400 mr-0.5">Format:</span>
                {TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setSelectedTemplate(t.id)}
                    disabled={isProcessing}
                    className={`text-xs px-2.5 py-1 rounded-full border transition ${
                      selectedTemplate === t.id
                        ? "bg-brand-600 text-white border-brand-600"
                        : "bg-white text-slate-500 border-slate-200 hover:border-brand-400 hover:text-brand-600 disabled:opacity-40"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            )}

            <form onSubmit={handleSubmit} className="flex gap-3">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  clarification.needed
                    ? "Type your clarification…"
                    : currentTemplate.placeholder
                }
                disabled={isProcessing && !clarification.needed}
                className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent disabled:opacity-50 transition"
              />
              <button
                type="submit"
                disabled={(isProcessing && !clarification.needed) || !input.trim()}
                className="px-5 py-3 bg-brand-600 text-white text-sm font-medium rounded-xl hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                {clarification.needed ? "Submit" : "Send"}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Welcome screen ─────────────────────────────────────────────────────────────

const EXAMPLES: { title: string; example: string; template?: TemplateId }[] = [
  {
    title: "Company research",
    example: "Research NVIDIA's latest AI partnerships",
  },
  {
    title: "Investor memo",
    example: "Analyse OpenAI as an investment opportunity",
    template: "investor_memo",
  },
  {
    title: "SWOT analysis",
    example: "SWOT analysis of Apple Inc.",
    template: "swot",
  },
  {
    title: "Comparison",
    example: "Compare Tesla vs Rivian: strategy and financials",
    template: "comparison",
  },
];

function WelcomeScreen({
  onExampleClick,
}: {
  onExampleClick: (text: string, template?: TemplateId) => void;
}) {
  return (
    <div className="text-center py-16">
      <div className="w-14 h-14 rounded-2xl bg-brand-600 flex items-center justify-center mx-auto mb-4">
        <span className="text-white text-2xl font-bold">C</span>
      </div>
      <h2 className="text-xl font-semibold text-slate-800 mb-2">
        Welcome to ClarityAI
      </h2>
      <p className="text-sm text-slate-500 max-w-sm mx-auto mb-8">
        AI-powered business intelligence through collaborative multi-agent
        reasoning.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl mx-auto text-left">
        {EXAMPLES.map((item) => (
          <button
            key={item.title}
            type="button"
            onClick={() => onExampleClick(item.example, item.template)}
            className="bg-white border border-slate-200 rounded-xl px-4 py-3 shadow-sm text-left hover:border-brand-400 hover:shadow-md transition cursor-pointer"
          >
            <p className="text-xs font-medium text-brand-600 mb-1">{item.title}</p>
            <p className="text-xs text-slate-500">{item.example}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
