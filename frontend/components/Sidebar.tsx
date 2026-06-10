"use client";

import { Conversation } from "@/types";

interface SidebarProps {
  open: boolean;
  conversations: Conversation[];
  currentThreadId: string | null;
  onSelect: (conv: Conversation) => void;
  onDelete: (id: string) => void;
  onNewChat: () => void;
}

export default function Sidebar({
  open,
  conversations,
  currentThreadId,
  onSelect,
  onDelete,
  onNewChat,
}: SidebarProps) {
  if (!open) return null;

  return (
    <div className="w-60 bg-white border-r border-slate-200 flex flex-col flex-shrink-0 h-full">
      {/* New chat button */}
      <div className="px-3 py-3 border-b border-slate-200">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 transition"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New Chat
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto custom-scroll py-2">
        {conversations.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-slate-400">
            No conversations yet
          </p>
        ) : (
          conversations.map((conv) => (
            <ConversationItem
              key={conv.id}
              conv={conv}
              active={conv.threadId === currentThreadId}
              onSelect={onSelect}
              onDelete={onDelete}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ConversationItem({
  conv,
  active,
  onSelect,
  onDelete,
}: {
  conv: Conversation;
  active: boolean;
  onSelect: (c: Conversation) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div
      className={`group flex items-start gap-1 px-2 py-1.5 mx-2 rounded-lg cursor-pointer transition ${
        active ? "bg-brand-50" : "hover:bg-slate-50"
      }`}
      onClick={() => onSelect(conv)}
    >
      <div className="flex-1 min-w-0 py-0.5">
        <p className="text-xs font-medium text-slate-700 truncate leading-snug">
          {conv.title}
        </p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-[10px] text-slate-400">{formatDate(conv.createdAt)}</span>
          {conv.template !== "standard" && (
            <span className="text-[10px] px-1.5 py-px bg-slate-100 text-slate-500 rounded-full capitalize">
              {conv.template.replace("_", " ")}
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(conv.id);
        }}
        className="opacity-0 group-hover:opacity-100 mt-1 p-0.5 text-slate-300 hover:text-red-400 transition flex-shrink-0"
        title="Delete conversation"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
