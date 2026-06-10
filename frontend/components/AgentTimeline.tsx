"use client";

import { AgentStep } from "@/types";

interface AgentTimelineProps {
  steps: AgentStep[];
}

const STATUS_ICON: Record<AgentStep["status"], string> = {
  pending: "○",
  running: "◌",
  completed: "✓",
  error: "✗",
};

const STATUS_COLOR: Record<AgentStep["status"], string> = {
  pending: "text-slate-400",
  running: "text-brand-500 animate-pulse",
  completed: "text-emerald-500",
  error: "text-red-500",
};

function stepDetail(step: AgentStep): string | null {
  if (!step.output) return null;
  const { clarity_status, confidence_score, validation_result } = step.output as Record<
    string,
    unknown
  >;
  if (clarity_status === "clear") return "query is clear";
  if (typeof confidence_score === "number") return `confidence ${confidence_score}/10`;
  if (validation_result) return String(validation_result);
  return null;
}

export default function AgentTimeline({ steps }: AgentTimelineProps) {
  if (steps.length === 0) return null;

  return (
    <div className="mt-2 mb-3 pl-1">
      <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
        Agent Activity
      </p>
      <div className="space-y-1.5">
        {steps.map((step, i) => {
          const detail = stepDetail(step);
          return (
            <div key={i} className="flex items-center gap-2">
              <span
                className={`text-sm font-mono w-4 text-center flex-shrink-0 ${STATUS_COLOR[step.status]}`}
              >
                {STATUS_ICON[step.status]}
              </span>
              <span className="text-xs text-slate-600">{step.agent}</span>
              {detail && (
                <span className="text-xs text-slate-400">— {detail}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
