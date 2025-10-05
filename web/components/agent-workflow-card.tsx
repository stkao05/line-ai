import type { ReactNode } from "react";

export type AgentWorkflowStatus = "complete" | "active" | "pending";

export type AgentWorkflowStep = {
  title: string;
  detail: ReactNode;
  status: AgentWorkflowStatus;
};

type AgentWorkflowCardProps = {
  title: string;
  steps: AgentWorkflowStep[];
  placeholder?: ReactNode;
};

const DEFAULT_PLACEHOLDER = (
  <div className="rounded-2xl border border-dashed border-zinc-800 bg-zinc-900/30 px-4 py-5 text-sm text-zinc-500">
    Agent workflow updates will appear here once messages arrive.
  </div>
);

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
          <div key={`${step.title}-${index}`} className="flex items-start gap-4">
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

function deriveSubtitle(steps: AgentWorkflowStep[]): string {
  const startedSteps = steps.filter((step) => step.status !== "pending");
  const currentStep = startedSteps[startedSteps.length - 1];

  if (!currentStep) {
    return "Waiting for agent activity";
  }

  const completionLabel =
    currentStep.status === "complete" ? "Complete" : "In Progress";
  return `${currentStep.title} · ${completionLabel}`;
}

export function AgentWorkflowCard({
  title,
  steps,
  placeholder,
}: AgentWorkflowCardProps) {
  const visibleSteps = steps.filter((step) => step.status !== "pending");
  const subtitle = deriveSubtitle(steps);
  const hasWorkflowActivity = visibleSteps.length > 0;

  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-5">
      <div className="flex items-center justify-between gap-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          {title}
        </p>
        <span className="text-xs text-zinc-500">{subtitle}</span>
      </div>
      <div className="mt-5 space-y-6">
        {hasWorkflowActivity ? (
          <WorkflowTrack steps={visibleSteps} />
        ) : (
          (placeholder ?? DEFAULT_PLACEHOLDER)
        )}
      </div>
    </section>
  );
}
