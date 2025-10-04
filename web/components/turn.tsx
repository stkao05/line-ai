import type { ReactNode } from "react";
import type { PageSummary, StreamMessage, TurnData } from "../types";
import {
  AgentWorkflowCard,
  type AgentWorkflowStep,
  type AgentWorkflowStatus,
} from "./agent-workflow-card";
import { AnswerSection, type TurnReference } from "./answer-section";
import { EXAMPLE_TURN } from "../components/turn.fixtures";

export type { TurnData } from "../types";
export type {
  AgentWorkflowStep,
  AgentWorkflowStatus,
} from "./agent-workflow-card";
export type { TurnReference } from "./answer-section";

const AGENT_WORKFLOW_TITLE = "Agent Workflow";

type TurnStartMessage = Extract<StreamMessage, { type: "turn.start" }>;
type SearchStartMessage = Extract<StreamMessage, { type: "search.start" }>;
type SearchEndMessage = Extract<StreamMessage, { type: "search.end" }>;
type RankStartMessage = Extract<StreamMessage, { type: "rank.start" }>;
type RankEndMessage = Extract<StreamMessage, { type: "rank.end" }>;
type FetchStartMessage = Extract<StreamMessage, { type: "fetch.start" }>;
type FetchEndMessage = Extract<StreamMessage, { type: "fetch.end" }>;
type AnswerDeltaMessage = Extract<StreamMessage, { type: "answer-delta" }>;
type AnswerMessage = Extract<StreamMessage, { type: "answer" }>;

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
  const turnStarts = messages.filter(
    (message): message is TurnStartMessage => message.type === "turn.start"
  );
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
  const answerDetail = rawFinalAnswer
    ? "Final response prepared."
    : answerDeltas.length > 0
      ? "Composing response…"
      : "Waiting for synthesis step.";

  const hasTurnStart = turnStarts.length > 0;
  const hasAnyWorkflowMessageBeyondTurnStart = messages.some(
    (message) => message.type !== "turn.start"
  );
  const thinkingStatus: AgentWorkflowStatus = hasTurnStart
    ? hasAnyWorkflowMessageBeyondTurnStart
      ? "complete"
      : "active"
    : "pending";
  const thinkingDetail = hasTurnStart
    ? "Assessing the question before taking action."
    : "Waiting for the agent to begin.";

  return [
    {
      title: "Thinking through the request",
      status: thinkingStatus,
      detail: thinkingDetail,
    },
    {
      title: "Searching the knowledge base",
      status: computeStepStatus(searchStarts.length > 0, searchEnds.length > 0),
      detail: searchDetail,
    },
    {
      title: "Ranking potential sources",
      status: computeStepStatus(rankStarts.length > 0, Boolean(latestRankEnd)),
      detail: rankDetail,
    },
    {
      title: "Fetching supporting details",
      status: computeStepStatus(
        fetchStarts.length > 0,
        Boolean(latestFetchEnd)
      ),
      detail: fetchDetail,
    },
    {
      title: "Answering the question",
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
          <AgentWorkflowCard title={AGENT_WORKFLOW_TITLE} steps={steps} />
          <AnswerSection content={answerContent} references={references} />
        </div>
      </section>
    </div>
  );
}
