import type { ReactNode } from "react";

export type AgentWorkflowStatus = "complete" | "active" | "pending";

export type AgentWorkflowStep = {
  title: string;
  detail: string;
  status: AgentWorkflowStatus;
};

export type TurnReference = {
  title: string;
  description: string;
  href: string;
};

export type TurnData = {
  question: string;
  agentWorkflow: {
    title: string;
    steps: AgentWorkflowStep[];
  };
  answer: {
    content: string;
    references: TurnReference[];
  };
};

const EXAMPLE_TURN: TurnData = {
  question:
    "What is the fastest way to get up to speed with Rust if I already write a lot of JavaScript?",
  agentWorkflow: {
    title: "Agent Workflow",
    steps: [
      {
        title: "Plan",
        detail:
          "Planner decomposes the query into clear stages and deliverables.",
        status: "complete",
      },
      {
        title: "Research",
        detail:
          "Parallel retrievers fan out with web search, internal knowledge, and code search.",
        status: "complete",
      },
      {
        title: "Filter",
        detail:
          "Re-rankers discard noise and surface the most relevant supporting docs.",
        status: "complete",
      },
      {
        title: "Synthesize",
        detail:
          "LLM drafts the answer, citing evidence and surfacing open questions.",
        status: "active",
      },
    ],
  },
  answer: {
    content: `Rust rewards learning by building. Start with a concise primer on ownership and borrowing, then move directly into shipping a small CLI where you can feel the compiler guiding you. Coming from JavaScript, the type system will feel stricter, so embrace compiler errors as checklists for what to adjust next.

### How to ramp quickly
- Alternate between high-signal resources like the Rust Book, Rustlings, and Rust by Example.
- Port a familiar JS utility into Rust to create one-to-one pattern mapping.
- Capture borrow-checker learnings so you can reuse them later.

Once you are comfortable with the borrow checker, explore async Rust and ecosystem crates: Tokio for async runtimes, Axum or Actix for web services, and Serde for data handling. Keep notes on how you solved borrow checker puzzles; it accelerates future debugging and mirrors Perplexity's habit of surfacing reasoning alongside answers.`,
    references: [
      {
        title: "The Rust Programming Language",
        description:
          "Foundational chapters on ownership, lifetimes, and error handling.",
        href: "https://doc.rust-lang.org/book/",
      },
      {
        title: "Rustlings Exercises",
        description:
          "Bite-sized tasks that drill the borrow checker and pattern matching.",
        href: "https://github.com/rust-lang/rustlings",
      },
      {
        title: "Rust by Example",
        description:
          "Annotated snippets for quick translation from JavaScript concepts.",
        href: "https://rust-by-example.github.io/",
      },
    ],
  },
};

function renderInlineMarkdown(text: string): ReactNode[] {
  const segments = text
    .split(/(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g)
    .filter(Boolean);

  return segments.map((segment, index) => {
    if (segment.startsWith("**") && segment.endsWith("**")) {
      return <strong key={index}>{segment.slice(2, -2)}</strong>;
    }

    if (segment.startsWith("_") && segment.endsWith("_")) {
      return <em key={index}>{segment.slice(1, -1)}</em>;
    }

    if (segment.startsWith("`") && segment.endsWith("`")) {
      return (
        <code
          key={index}
          className="rounded bg-zinc-900 px-[6px] py-[2px] text-sm text-emerald-300"
        >
          {segment.slice(1, -1)}
        </code>
      );
    }

    return <span key={index}>{segment}</span>;
  });
}

function renderMarkdown(content: string): ReactNode[] {
  const elements: ReactNode[] = [];
  const lines = content.split("\n");
  let listBuffer: string[] = [];
  let codeBuffer: string[] = [];
  let inCodeBlock = false;

  const flushList = () => {
    if (listBuffer.length === 0) {
      return;
    }

    elements.push(
      <ul key={`list-${elements.length}`} className="list-disc space-y-2 pl-6">
        {listBuffer.map((item, index) => (
          <li key={index} className="text-sm text-zinc-300">
            {renderInlineMarkdown(item)}
          </li>
        ))}
      </ul>
    );

    listBuffer = [];
  };

  const flushCode = () => {
    if (!inCodeBlock) {
      return;
    }

    elements.push(
      <pre
        key={`code-${elements.length}`}
        className="overflow-x-auto rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4 text-sm"
      >
        <code>{codeBuffer.join("\n")}</code>
      </pre>
    );

    codeBuffer = [];
    inCodeBlock = false;
  };

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (trimmed.startsWith("```") || trimmed.startsWith("~~~")) {
      if (!inCodeBlock) {
        flushList();
        inCodeBlock = true;
        codeBuffer = [];
      } else {
        flushCode();
      }
      return;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      return;
    }

    if (trimmed.length === 0) {
      flushList();
      return;
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      listBuffer.push(trimmed.replace(/^[-*+]\s+/, ""));
      return;
    }

    flushList();

    if (/^#{1,6}\s+/.test(trimmed)) {
      const level = Math.min(trimmed.match(/^#{1,6}/)?.[0].length ?? 1, 6);
      const HeadingTag = `h${level}` as keyof JSX.IntrinsicElements;
      const text = trimmed.replace(/^#{1,6}\s+/, "");

      elements.push(
        <HeadingTag
          key={`heading-${elements.length}`}
          className="text-lg font-semibold text-zinc-100"
        >
          {renderInlineMarkdown(text)}
        </HeadingTag>
      );
      return;
    }

    elements.push(
      <p
        key={`paragraph-${elements.length}`}
        className="text-base leading-relaxed text-zinc-200"
      >
        {renderInlineMarkdown(line)}
      </p>
    );
  });

  flushList();
  flushCode();

  return elements;
}

export function Turn({ turn = EXAMPLE_TURN }: { turn?: TurnData }) {
  const { agentWorkflow, question, answer } = turn;
  const steps = agentWorkflow.steps;
  const totalSteps = steps.length || 1;
  const activeIndex = steps.findIndex((step) => step.status === "active");
  const completedCount = steps.filter(
    (step) => step.status === "complete"
  ).length;
  const stepPosition =
    activeIndex !== -1
      ? activeIndex + 1
      : completedCount > 0
        ? Math.min(completedCount, totalSteps)
        : 1;

  return (
    <div className="w-auto space-y-8 py-10 text-zinc-100">
      <section className="overflow-hidden rounded-3xl border border-zinc-800 bg-zinc-950/60 shadow-xl shadow-black/20">
        <header className="space-y-2 border-b border-zinc-800 bg-zinc-950/80 px-6 py-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Question
          </p>
          <p className="text-lg font-medium leading-7 text-zinc-50">
            {question}
          </p>
        </header>

        <div className="space-y-6 px-6 py-7">
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-5">
            <div className="flex items-center justify-between gap-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
                {agentWorkflow.title}
              </p>
              <span className="text-xs text-zinc-500">
                Step {stepPosition} of {totalSteps}
              </span>
            </div>
            <ol className="mt-5 space-y-5">
              {steps.map((step, index) => {
                const isActive = step.status === "active";
                const isComplete = step.status === "complete";
                const statusLabel = isActive
                  ? "In Progress"
                  : isComplete
                    ? "Complete"
                    : "Pending";

                return (
                  <li key={step.title} className="relative pl-9">
                    {index < steps.length - 1 ? (
                      <span
                        className="absolute left-[11px] top-6 h-full w-px bg-zinc-800"
                        aria-hidden
                      />
                    ) : null}
                    <span
                      className={`absolute left-0 top-0 flex h-6 w-6 items-center justify-center rounded-full border text-xs font-semibold ${
                        isActive
                          ? "border-emerald-400 bg-emerald-400/10 text-emerald-300"
                          : isComplete
                            ? "border-zinc-500 bg-zinc-800 text-zinc-200"
                            : "border-zinc-700 bg-zinc-900 text-zinc-400"
                      }`}
                    >
                      {index + 1}
                    </span>
                    <div className="flex flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-3">
                        <p className="text-sm font-semibold text-zinc-100">
                          {step.title}
                        </p>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-widest ${
                            isActive
                              ? "border-emerald-400/60 bg-emerald-400/10 text-emerald-200"
                              : isComplete
                                ? "border-zinc-600 bg-zinc-800 text-zinc-300"
                                : "border-zinc-700 bg-zinc-900 text-zinc-500"
                          }`}
                        >
                          {statusLabel}
                        </span>
                      </div>
                      <p className="text-sm text-zinc-400">{step.detail}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>

          <div className="space-y-6">
            <div className="space-y-4 text-base leading-relaxed text-zinc-200">
              {renderMarkdown(answer.content)}
            </div>

            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
                References
              </p>
              <div className="grid gap-3 md:grid-cols-3">
                {answer.references.map((reference) => (
                  <a
                    key={reference.href}
                    className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4 transition hover:border-emerald-400/60 hover:text-emerald-200"
                    href={reference.href}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <p className="text-sm font-semibold">{reference.title}</p>
                    <p className="mt-1 text-xs text-zinc-400">
                      {reference.description}
                    </p>
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
