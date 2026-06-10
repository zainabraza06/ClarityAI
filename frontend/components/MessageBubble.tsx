"use client";

import { useState } from "react";
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

  const filename = `clarity-report-${new Date(message.timestamp)
    .toISOString()
    .slice(0, 10)}.md`;

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] group">
        {/* Agent timeline shown above the response */}
        {message.agentSteps && message.agentSteps.length > 0 && (
          <div className="bg-white border border-slate-100 rounded-xl px-4 py-3 mb-2 shadow-sm">
            <AgentTimeline steps={message.agentSteps} />
          </div>
        )}

        <div className="bg-white border border-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
          {/* Content + action buttons */}
          <div className="flex items-start gap-2">
            <div className="prose-chat flex-1 min-w-0">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
            <div className="flex gap-1 flex-shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <CopyButton content={message.content} />
              <DownloadButton content={message.content} filename={filename} />
            </div>
          </div>

          {/* Bottom row: confidence badge + sources */}
          {(message.confidenceScore !== undefined ||
            (message.sources && message.sources.length > 0)) && (
            <div className="mt-3 pt-2 border-t border-slate-100 space-y-2">
              {message.confidenceScore !== undefined && (
                <ConfidenceBadge score={message.confidenceScore} />
              )}
              {message.sources && message.sources.length > 0 && (
                <SourcesList sources={message.sources} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function CopyButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={copied ? "Copied!" : "Copy report"}
      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
    >
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}

function DownloadButton({ content, filename }: { content: string; filename: string }) {
  const handleDownload = () => {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <button
      type="button"
      onClick={handleDownload}
      title="Download as Markdown"
      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
    </button>
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

function SourcesList({ sources }: { sources: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? sources : sources.slice(0, 3);

  return (
    <div>
      <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-1">
        Sources
      </p>
      <div className="space-y-0.5">
        {visible.map((src, i) => (
          <a
            key={i}
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-xs text-brand-600 hover:underline truncate"
          >
            {src}
          </a>
        ))}
      </div>
      {sources.length > 3 && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-1 text-xs text-slate-400 hover:text-slate-600 transition"
        >
          {expanded ? "Show less" : `+${sources.length - 3} more`}
        </button>
      )}
    </div>
  );
}
