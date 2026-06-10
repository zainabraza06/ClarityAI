"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage } from "@/types";
import AgentTimeline from "./AgentTimeline";

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-brand-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        {/* Agent timeline shown above the response */}
        {message.agentSteps && message.agentSteps.length > 0 && (
          <div className="bg-white border border-slate-100 rounded-xl px-4 py-3 mb-2 shadow-sm">
            <AgentTimeline steps={message.agentSteps} />
          </div>
        )}

        <div className="bg-white border border-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
          <div className="prose-chat">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>

          {/* Confidence score badge */}
          {message.confidenceScore !== undefined && (
            <div className="mt-3 pt-2 border-t border-slate-100">
              <ConfidenceBadge score={message.confidenceScore} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfidenceBadge({ score }: { score: number }) {
  const color =
    score >= 7
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : score >= 5
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-red-50 text-red-700 border-red-200";

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium ${color}`}
    >
      Research confidence: {score}/10
    </span>
  );
}
