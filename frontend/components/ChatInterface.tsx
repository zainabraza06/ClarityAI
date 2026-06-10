"use client";

import { useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { AgentStep, ChatMessage, SSEEvent } from "@/types";
import MessageBubble from "./MessageBubble";
import AgentTimeline from "./AgentTimeline";

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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveSteps, isProcessing]);

  // ---------- Core send logic ----------

  const sendMessage = async (text: string) => {
    if (!text.trim() || isProcessing) return;

    const currentThreadId = threadId || uuidv4();
    if (!threadId) setThreadId(currentThreadId);

    // Add user message to the UI immediately
    setMessages((prev) => [
      ...prev,
      {
        id: uuidv4(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
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
        body: JSON.stringify({ message: text, thread_id: currentThreadId }),
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
    } catch (err) {
      appendAssistantMessage(
        "Sorry, something went wrong. Please try again.",
        collectedSteps,
        undefined,
        currentThreadId
      );
    } finally {
      setIsProcessing(false);
      setLiveSteps([]);
    }
  };

  // ---------- SSE event handler ----------

  const handleSSEEvent = (
    event: SSEEvent,
    collectedSteps: AgentStep[],
    currentThreadId: string
  ) => {
    if (event.thread_id) setThreadId(event.thread_id);

    switch (event.type) {
      case "agent_start": {
        const step: AgentStep = {
          agent: event.agent ?? "",
          status: "running",
        };
        collectedSteps.push(step);
        // Update live display
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
          event.thread_id ?? currentThreadId
        );
        break;
      }

      case "error": {
        appendAssistantMessage(
          `Research error: ${event.message}`,
          [...collectedSteps],
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
    _threadId: string
  ) => {
    setMessages((prev) => [
      ...prev,
      {
        id: uuidv4(),
        role: "assistant",
        content,
        timestamp: new Date().toISOString(),
        agentSteps: steps,
        confidenceScore,
      },
    ]);
  };

  const findLastRunning = (steps: AgentStep[], agentName: string): number => {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].agent === agentName && steps[i].status === "running") return i;
    }
    return -1;
  };

  // ---------- Form handlers ----------

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (clarification.needed) {
      submitClarification(input);
    } else {
      sendMessage(input);
    }
  };

  const submitClarification = (text: string) => {
    if (!text.trim()) return;
    setClarification({ needed: false, question: "" });
    sendMessage(text);
  };

  // ---------- Render ----------

  const isEmpty = messages.length === 0 && !isProcessing;

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center gap-3 shadow-sm">
        <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
          <span className="text-white text-sm font-bold">C</span>
        </div>
        <div>
          <h1 className="text-base font-semibold text-slate-900">ClarityAI</h1>
          <p className="text-xs text-slate-500">Multi-agent business research</p>
        </div>
        {threadId && (
          <span className="ml-auto text-xs text-slate-300 font-mono truncate max-w-[200px]">
            {threadId.slice(0, 8)}…
          </span>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto custom-scroll px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {isEmpty && <WelcomeScreen />}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Live agent progress while processing */}
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

          {/* Initial spinner before first SSE event */}
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
        <div className="border-t border-amber-200 bg-amber-50 px-4 py-3">
          <div className="max-w-3xl mx-auto">
            <p className="text-sm text-amber-800 font-medium mb-1">
              Clarification needed
            </p>
            <p className="text-sm text-amber-700">{clarification.question}</p>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="bg-white border-t border-slate-200 px-4 py-4">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto flex gap-3">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              clarification.needed
                ? "Type your clarification…"
                : "Ask about any company — e.g. 'Research NVIDIA's AI strategy'"
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
  );
}

function WelcomeScreen() {
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
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-xl mx-auto text-left">
        {[
          {
            title: "Direct research",
            example: "Research NVIDIA's latest AI partnerships",
          },
          {
            title: "Company analysis",
            example: "What are OpenAI's recent developments?",
          },
          {
            title: "Follow-up questions",
            example: "What about their main competitors?",
          },
        ].map((item) => (
          <div
            key={item.title}
            className="bg-white border border-slate-200 rounded-xl px-4 py-3 shadow-sm"
          >
            <p className="text-xs font-medium text-brand-600 mb-1">
              {item.title}
            </p>
            <p className="text-xs text-slate-500">{item.example}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
