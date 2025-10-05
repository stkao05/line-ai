import type { ReactNode } from "react";

export type AgentWorkflowStatus = "complete" | "active" | "pending";

export type AgentWorkflowStep = {
  title: string;
  detail: ReactNode;
  status: AgentWorkflowStatus;
};

type AgentWorkflowCardProps = {
  steps: AgentWorkflowStep[];
};

type WorkflowTrackProps = {
  steps: AgentWorkflowStep[];
};

function WorkflowTrack({ steps }: WorkflowTrackProps) {
  return (
    <div className="space-y-5">
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;
        const isActive = step.status === "active";
        const isComplete = step.status === "complete";
        const dotClassName = `relative h-3 w-3 rounded-full border transition ${
          isActive
            ? "border-emerald-300 bg-emerald-300"
            : isComplete
              ? "border-zinc-500 bg-zinc-500"
              : "border-zinc-600 bg-zinc-800"
        }`;
        const connectorClassName = `mt-1 flex-1 w-px transition-colors ${
          isActive
            ? "bg-emerald-300/60 animate-pulse"
            : isComplete
              ? "bg-zinc-600"
              : "bg-zinc-700"
        }`;
        const titleClassName = `text-sm font-semibold transition ${
          isActive
            ? "text-zinc-50 glow-text-fast"
            : isComplete
              ? "text-zinc-100"
              : "text-zinc-500"
        }`;
        const detailClassName = `text-sm transition-colors ${
          isActive ? "text-zinc-300" : "text-zinc-400"
        }`;

        return (
          <div
            key={`${step.title}-${index}`}
            className="flex items-start gap-4"
          >
            <div className="flex flex-col items-center self-stretch">
              <span className="relative flex h-6 w-6 items-center justify-center">
                {isActive ? (
                  <span className="absolute h-6 w-6 rounded-full bg-emerald-400/40 blur-md glow-dot-fast" />
                ) : null}
                <span className={dotClassName} />
              </span>
              {!isLast ? (
                <span className={connectorClassName} />
              ) : (
                <span className="flex-1" />
              )}
            </div>
            <div className="flex-1 space-y-1">
              <p className={titleClassName}>{step.title}</p>
              <div className={detailClassName}>{step.detail}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function AgentWorkflowCard({ steps }: AgentWorkflowCardProps) {
  const visibleSteps = steps.filter((step) => step.status !== "pending");
  const hasWorkflowActivity = visibleSteps.length > 0;

  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-5">
      <div className="flex items-center justify-between gap-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          STEPS
        </p>
      </div>
      <div className="mt-5 space-y-6">
        {hasWorkflowActivity ? (
          <WorkflowTrack steps={visibleSteps} />
        ) : (
          <svg
            className="size-5 animate-spin text-white"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            ></circle>
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            ></path>
          </svg>
        )}
      </div>
    </section>
  );
}
