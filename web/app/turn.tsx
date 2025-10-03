import type { ReactNode } from "react";
import type { PageSummary, StreamMessage, TurnData } from "./types";
export type { TurnData } from "./types";

export type AgentWorkflowStatus = "complete" | "active" | "pending";

export type AgentWorkflowStep = {
  title: string;
  detail: ReactNode;
  status: AgentWorkflowStatus;
};

type SearchStartMessage = Extract<StreamMessage, { type: "search.start" }>;
type SearchEndMessage = Extract<StreamMessage, { type: "search.end" }>;
type RankStartMessage = Extract<StreamMessage, { type: "rank.start" }>;
type RankEndMessage = Extract<StreamMessage, { type: "rank.end" }>;
type FetchStartMessage = Extract<StreamMessage, { type: "fetch.start" }>;
type FetchEndMessage = Extract<StreamMessage, { type: "fetch.end" }>;
type AnswerDeltaMessage = Extract<StreamMessage, { type: "answer-delta" }>;
type AnswerMessage = Extract<StreamMessage, { type: "answer" }>;

export type TurnReference = {
  title: string;
  description: string;
  href: string;
};

const AGENT_WORKFLOW_TITLE = "Agent Workflow";

const EXAMPLE_PAGES: PageSummary[] = [
  {
    url: "https://doc.rust-lang.org/book/",
    title: "The Rust Programming Language",
    snippet:
      "Foundational chapters on ownership, lifetimes, and error handling.",
    favicon: "https://doc.rust-lang.org/favicon.ico",
  },
  {
    url: "https://github.com/rust-lang/rustlings",
    title: "Rustlings Exercises",
    snippet:
      "Bite-sized tasks that drill the borrow checker and pattern matching.",
    favicon: "https://avatars.githubusercontent.com/u/5430905?s=200&v=4",
  },
  {
    url: "https://rust-by-example.github.io/",
    title: "Rust by Example",
    snippet:
      "Annotated snippets for quick translation from JavaScript concepts.",
    favicon: "https://rust-by-example.github.io/favicon.ico",
  },
];

const EXAMPLE_TURN: TurnData = {
  question:
    "What is the fastest way to get up to speed with Rust if I already write a lot of JavaScript?",
  messages: [
    {
      type: "search.start",
      query: "fastest way to learn rust for javascript developers",
    },
    {
      type: "search.end",
      query: "fastest way to learn rust for javascript developers",
      results: 18,
    },
    {
      type: "rank.start",
    },
    {
      type: "rank.end",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "fetch.start",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "fetch.end",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "answer-delta",
      delta:
        "Rust rewards learning by building. Start with a concise primer on ownership and borrowing, then move directly into shipping a small CLI where you can feel the compiler guiding you.",
    },
  ],
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

function getLast<T>(items: readonly T[]): T | undefined {
  if (items.length === 0) {
    return undefined;
  }
  return items[items.length - 1];
}

function findLast<T>(
  items: readonly T[],
  predicate: (value: T) => boolean
): T | undefined {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const value = items[index];
    if (predicate(value)) {
      return value;
    }
  }
  return undefined;
}

function truncate(text: string, maxLength = 200): string {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

function renderPageList(
  pages: PageSummary[],
  options?: { variant?: "default" | "fetch" }
): ReactNode {
  const uniquePages: PageSummary[] = [];
  const seen = new Set<string>();
  const variant = options?.variant ?? "default";

  for (const page of pages) {
    if (!page.url) {
      continue;
    }
    if (seen.has(page.url)) {
      continue;
    }
    seen.add(page.url);
    uniquePages.push(page);
    if (uniquePages.length >= 4) {
      break;
    }
  }

  if (uniquePages.length === 0) {
    return <span>No pages available.</span>;
  }

  return (
    <ul className="space-y-2">
      {uniquePages.map((page) => {
        const title = page.title?.trim() || page.url;
        const snippet = page.snippet?.trim();
        const favicon = page.favicon?.trim();
        const displayUrl = truncate(page.url, 120);

        if (variant === "fetch") {
          return (
            <li key={page.url} className="flex items-start gap-3">
              {favicon ? (
                <img
                  src={favicon}
                  alt=""
                  className="h-6 w-6 shrink-0 rounded-full border border-zinc-800"
                />
              ) : (
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-[10px] text-zinc-500">
                  {title.slice(0, 1).toUpperCase()}
                </span>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-zinc-400">
                  {title}
                </span>
                <a
                  href={page.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-zinc-500 hover:text-emerald-200"
                >
                  {displayUrl}
                </a>
              </div>
            </li>
          );
        }

        return (
          <li key={page.url} className="space-y-0.5">
            <span>{title}</span>
            {snippet ? (
              <span className="block text-xs text-zinc-500">
                {truncate(snippet, 160)}
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function computeStepStatus(
  hasStarted: boolean,
  hasCompleted: boolean
): AgentWorkflowStatus {
  if (hasCompleted) {
    return "complete";
  }
  if (hasStarted) {
    return "active";
  }
  return "pending";
}

function buildWorkflowSteps(messages: StreamMessage[]): AgentWorkflowStep[] {
  const searchStarts = messages.filter(
    (message): message is SearchStartMessage => message.type === "search.start"
  );
  const searchEnds = messages.filter(
    (message): message is SearchEndMessage => message.type === "search.end"
  );
  const searchQueries = Array.from(
    new Set([...searchStarts, ...searchEnds].map((message) => message.query))
  );
  const searchDetail =
    searchQueries.length === 0 ? (
      "Waiting for search to begin."
    ) : (
      <ul className="space-y-1">
        {searchQueries.map((query) => {
          const endMessage = findLast(
            searchEnds,
            (message) => message.query === query
          );
          const resultLabel = endMessage
            ? `${endMessage.results} result${endMessage.results === 1 ? "" : "s"}`
            : "Searching…";

          return (
            <li key={query} className="space-y-0.5">
              <span>“{query}”</span>
              <span className="block text-xs text-zinc-500">{resultLabel}</span>
            </li>
          );
        })}
      </ul>
    );

  const rankStarts = messages.filter(
    (message): message is RankStartMessage => message.type === "rank.start"
  );
  const rankEnds = messages.filter(
    (message): message is RankEndMessage => message.type === "rank.end"
  );
  const latestRankEnd = getLast(rankEnds);
  const rankDetail = latestRankEnd
    ? `Ranked ${latestRankEnd.pages.length} candidate page${latestRankEnd.pages.length === 1 ? "" : "s"}.`
    : rankStarts.length > 0
      ? "Ranking candidate pages…"
      : "Waiting for ranking step.";

  const fetchStarts = messages.filter(
    (message): message is FetchStartMessage => message.type === "fetch.start"
  );
  const fetchEnds = messages.filter(
    (message): message is FetchEndMessage => message.type === "fetch.end"
  );
  const latestFetchEnd = getLast(fetchEnds);
  const fetchPages = latestFetchEnd?.pages ?? getLast(fetchStarts)?.pages ?? [];
  const fetchDetail =
    fetchPages && fetchPages.length > 0
      ? renderPageList(fetchPages, { variant: "fetch" })
      : fetchStarts.length > 0
        ? "Fetching selected sources…"
        : "Waiting for document fetch step.";

  const answerMessages = messages.filter(
    (message): message is AnswerMessage => message.type === "answer"
  );
  const answerDeltas = messages.filter(
    (message): message is AnswerDeltaMessage => message.type === "answer-delta"
  );
  const latestAnswer = getLast(answerMessages);
  const rawFinalAnswer = latestAnswer?.answer?.trim();
  const answerPreview = rawFinalAnswer
    ? truncate(rawFinalAnswer.replace(/\s+/g, " ").trim(), 160)
    : "";
  const answerDetail = rawFinalAnswer
    ? answerPreview
    : answerDeltas.length > 0
      ? "Composing response…"
      : "Waiting for synthesis step.";

  return [
    {
      title: "Search",
      status: computeStepStatus(searchStarts.length > 0, searchEnds.length > 0),
      detail: searchDetail,
    },
    {
      title: "Rank",
      status: computeStepStatus(rankStarts.length > 0, Boolean(latestRankEnd)),
      detail: rankDetail,
    },
    {
      title: "Fetch",
      status: computeStepStatus(
        fetchStarts.length > 0,
        Boolean(latestFetchEnd)
      ),
      detail: fetchDetail,
    },
    {
      title: "Answer",
      status: latestAnswer
        ? "complete"
        : answerDeltas.length > 0
          ? "active"
          : "pending",
      detail: answerDetail,
    },
  ];
}

function deriveReferencesFromPages(
  pages?: PageSummary[] | null
): TurnReference[] {
  if (!pages || pages.length === 0) {
    return [];
  }

  const references: TurnReference[] = [];
  const seen = new Set<string>();

  for (const page of pages) {
    if (!page.url || seen.has(page.url)) {
      continue;
    }
    seen.add(page.url);
    const title = page.title?.trim() || page.url;
    const description = page.snippet?.trim() || "No summary available.";
    references.push({
      title,
      description,
      href: page.url,
    });
  }

  return references;
}

function extractAnswer(messages: StreamMessage[]): {
  content: string;
  references: TurnReference[];
} {
  const answerMessages = messages.filter(
    (message): message is AnswerMessage => message.type === "answer"
  );
  const latestAnswer = getLast(answerMessages);
  const answerDeltas = messages.filter(
    (message): message is AnswerDeltaMessage => message.type === "answer-delta"
  );
  const combinedAnswer =
    latestAnswer?.answer ??
    answerDeltas.map((message) => message.delta).join("");

  const content = combinedAnswer ? combinedAnswer.trim() : "";
  const references = deriveReferencesFromPages(latestAnswer?.citations);

  return { content, references };
}

export function Turn({ turn = EXAMPLE_TURN }: { turn?: TurnData }) {
  const { question } = turn;
  const messages = turn.messages ?? [];
  const steps = buildWorkflowSteps(messages);
  const { content: answerContent, references } = extractAnswer(messages);

  const startedSteps = steps.filter((step) => step.status !== "pending");
  const currentStep = startedSteps[startedSteps.length - 1] ?? null;
  const workflowSubtitle = currentStep
    ? `${currentStep.title} · ${
        currentStep.status === "complete" ? "Complete" : "In Progress"
      }`
    : "Waiting for agent activity";
  const visibleSteps = steps.filter((step) => step.status !== "pending");
  const hasWorkflowActivity = visibleSteps.length > 0;

  const workflowPlaceholder = (
    <div className="rounded-2xl border border-dashed border-zinc-800 bg-zinc-900/30 px-4 py-5 text-sm text-zinc-500">
      Agent workflow updates will appear here once messages arrive.
    </div>
  );
  const renderWorkflowTrack = () => (
    <div className="space-y-5">
      {visibleSteps.map((step, index) => {
        const isLast = index === visibleSteps.length - 1;
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
          <div key={step.title} className="flex items-start gap-4">
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

  const hasAnswerContent = Boolean(answerContent.trim());
  const renderedAnswer = hasAnswerContent
    ? renderMarkdown(answerContent)
    : [
        <p
          key="placeholder"
          className="text-base leading-relaxed text-zinc-400"
        >
          Answer not available yet.
        </p>,
      ];

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
                {AGENT_WORKFLOW_TITLE}
              </p>
              <span className="text-xs text-zinc-500">{workflowSubtitle}</span>
            </div>
            <div className="mt-5 space-y-6">
              {hasWorkflowActivity
                ? renderWorkflowTrack()
                : workflowPlaceholder}
            </div>
          </section>

          <div className="space-y-6">
            <div className="space-y-4 text-base leading-relaxed text-zinc-200">
              {renderedAnswer}
            </div>

            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
                References
              </p>
              {references.length > 0 ? (
                <div className="grid gap-3 md:grid-cols-3">
                  {references.map((reference) => (
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
              ) : (
                <p className="text-sm text-zinc-500">
                  References will appear once sources are selected.
                </p>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
