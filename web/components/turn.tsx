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
type StepStartMessage = Extract<StreamMessage, { type: "step.start" }>;
type StepEndMessage = Extract<StreamMessage, { type: "step.end" }>;
type StepFetchStartMessage = Extract<StreamMessage, { type: "step.fetch.start" }>;
type StepFetchEndMessage = Extract<StreamMessage, { type: "step.fetch.end" }>;
type StepAnswerStartMessage = Extract<StreamMessage, { type: "step.answer.start" }>;
type StepAnswerDeltaMessage = Extract<StreamMessage, { type: "step.answer.delta" }>;
type StepAnswerEndMessage = Extract<StreamMessage, { type: "step.answer.end" }>;
type AnswerMessage = Extract<StreamMessage, { type: "answer" }>;

const PLANNING_STEP_TITLE = "Planning the appropriate route";
const SEARCH_STEP_TITLE = "Running web search";
const RANK_STEP_TITLE = "Ranking candidate sources";
const FETCH_STEP_TITLE = "Fetching supporting details";
const ANSWER_STEP_TITLE = "Answering the question";

function getLast<T>(items: readonly T[]): T | undefined {
  if (items.length === 0) {
    return undefined;
  }
  return items[items.length - 1];
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

function uniqueDescriptions(
  descriptions: readonly (string | null | undefined)[]
): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const description of descriptions) {
    const normalized = description?.trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    result.push(normalized);
  }

  return result;
}

function renderDescriptionItems(items: string[]): ReactNode {
  return (
    <ul className="space-y-1">
      {items.map((text) => (
        <li key={text}>{text}</li>
      ))}
    </ul>
  );
}

function buildWorkflowSteps(messages: StreamMessage[]): AgentWorkflowStep[] {
  const stepStarts = messages.filter(
    (message): message is StepStartMessage => message.type === "step.start"
  );
  const stepEnds = messages.filter(
    (message): message is StepEndMessage => message.type === "step.end"
  );
  const fetchStarts = messages.filter(
    (message): message is StepFetchStartMessage => message.type === "step.fetch.start"
  );
  const fetchEnds = messages.filter(
    (message): message is StepFetchEndMessage => message.type === "step.fetch.end"
  );
  const answerStarts = messages.filter(
    (message): message is StepAnswerStartMessage => message.type === "step.answer.start"
  );
  const answerDeltas = messages.filter(
    (message): message is StepAnswerDeltaMessage =>
      message.type === "step.answer.delta"
  );
  const answerEnds = messages.filter(
    (message): message is StepAnswerEndMessage => message.type === "step.answer.end"
  );
  const answerMessages = messages.filter(
    (message): message is AnswerMessage => message.type === "answer"
  );

  const planningStarts = stepStarts.filter(
    (message) => message.title === PLANNING_STEP_TITLE
  );
  const planningEnds = stepEnds.filter(
    (message) => message.title === PLANNING_STEP_TITLE
  );
  const planningDetail =
    uniqueDescriptions(planningEnds.map((message) => message.description))[0] ??
    uniqueDescriptions(planningStarts.map((message) => message.description))[0] ??
    "Waiting for planning step.";
  const planningStatus = computeStepStatus(
    planningStarts.length > 0,
    planningEnds.length > 0 && planningEnds.length >= planningStarts.length
  );

  const searchStarts = stepStarts.filter(
    (message) => message.title === SEARCH_STEP_TITLE
  );
  const searchEnds = stepEnds.filter(
    (message) => message.title === SEARCH_STEP_TITLE
  );
  const searchEndDescriptions = uniqueDescriptions(
    searchEnds.map((message) => message.description)
  );
  const searchStartDescriptions = uniqueDescriptions(
    searchStarts.map((message) => message.description)
  );
  const searchDetail: ReactNode = searchEndDescriptions.length > 0
    ? renderDescriptionItems(searchEndDescriptions)
    : searchStartDescriptions.length > 0
      ? renderDescriptionItems(searchStartDescriptions)
      : "Waiting for search to begin.";
  const searchStatus = computeStepStatus(
    searchStarts.length > 0,
    searchEnds.length > 0 && searchEnds.length >= searchStarts.length
  );

  const rankStarts = stepStarts.filter(
    (message) => message.title === RANK_STEP_TITLE
  );
  const rankEnds = stepEnds.filter(
    (message) => message.title === RANK_STEP_TITLE
  );
  const rankDetail =
    uniqueDescriptions(rankEnds.map((message) => message.description)).pop() ??
    uniqueDescriptions(rankStarts.map((message) => message.description)).pop() ??
    "Waiting for ranking step.";
  const rankStatus = computeStepStatus(
    rankStarts.length > 0,
    rankEnds.length > 0 && rankEnds.length >= rankStarts.length
  );

  const latestFetchEnd = getLast(fetchEnds);
  const latestFetchStart = getLast(fetchStarts);
  const fetchPages = latestFetchEnd?.pages ?? latestFetchStart?.pages ?? [];
  const fetchStatus = computeStepStatus(
    fetchStarts.length > 0,
    fetchEnds.length > 0 && fetchEnds.length >= fetchStarts.length
  );
  const fetchDetail: ReactNode = fetchPages.length > 0
    ? renderPageList(fetchPages, { variant: "fetch" })
    : fetchStatus === "active"
      ? "Fetching selected sources…"
      : "Waiting for document fetch step.";

  const answerHasStarted =
    answerStarts.length > 0 || answerDeltas.length > 0 || answerMessages.length > 0;
  const answerHasCompleted =
    answerMessages.length > 0 || answerEnds.length > 0;
  const answerStatus = computeStepStatus(answerHasStarted, answerHasCompleted);
  const answerIntro =
    uniqueDescriptions(answerStarts.map((message) => message.description))[0];
  const answerDetail = answerHasCompleted
    ? "Final response prepared."
    : answerDeltas.length > 0
      ? answerIntro ?? "Composing response…"
      : answerIntro ?? "Waiting for synthesis step.";

  return [
    {
      title: PLANNING_STEP_TITLE,
      status: planningStatus,
      detail: planningDetail,
    },
    {
      title: SEARCH_STEP_TITLE,
      status: searchStatus,
      detail: searchDetail,
    },
    {
      title: RANK_STEP_TITLE,
      status: rankStatus,
      detail: rankDetail,
    },
    {
      title: FETCH_STEP_TITLE,
      status: fetchStatus,
      detail: fetchDetail,
    },
    {
      title: ANSWER_STEP_TITLE,
      status: answerStatus,
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
    (message): message is StepAnswerDeltaMessage =>
      message.type === "step.answer.delta"
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
