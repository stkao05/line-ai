/* eslint-disable @next/next/no-img-element */
import type { ReactNode } from "react";
import type { PageSummary, StreamMessage, TurnData } from "../types";
import {
  AgentWorkflowCard,
  type AgentWorkflowStep,
  type AgentWorkflowStatus,
} from "./agent-workflow-card";
import { AnswerSection, type TurnReference } from "./answer-section";

export type { TurnData } from "../types";
export type {
  AgentWorkflowStep,
  AgentWorkflowStatus,
} from "./agent-workflow-card";
export type { TurnReference } from "./answer-section";

type StepStartMessage = Extract<StreamMessage, { type: "step.start" }>;
type StepStatusMessage = Extract<StreamMessage, { type: "step.status" }>;
type StepEndMessage = Extract<StreamMessage, { type: "step.end" }>;
type StepFetchStartMessage = Extract<
  StreamMessage,
  { type: "step.fetch.start" }
>;
type StepFetchEndMessage = Extract<StreamMessage, { type: "step.fetch.end" }>;
type StepAnswerStartMessage = Extract<
  StreamMessage,
  { type: "step.answer.start" }
>;
type StepAnswerDeltaMessage = Extract<
  StreamMessage,
  { type: "step.answer.delta" }
>;
type StepAnswerEndMessage = Extract<StreamMessage, { type: "step.answer.end" }>;
type AnswerMessage = Extract<StreamMessage, { type: "answer" }>;

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

        if (variant === "fetch") {
          return (
            <li key={page.url} className="flex items-center gap-2">
              {favicon ? (
                <img
                  src={favicon}
                  alt=""
                  className="h-4 w-4 shrink-0 rounded-full border border-zinc-800"
                />
              ) : (
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-[10px] text-zinc-500">
                  {title.slice(0, 1).toUpperCase()}
                </span>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <a
                  href={page.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-medium text-zinc-400 hover:text-line-200"
                >
                  {title}
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

type StepMessage =
  | StepStartMessage
  | StepStatusMessage
  | StepEndMessage
  | StepFetchStartMessage
  | StepFetchEndMessage
  | StepAnswerStartMessage
  | StepAnswerDeltaMessage
  | StepAnswerEndMessage;

type StepKind = "generic" | "fetch" | "answer";

type StepAccumulator = {
  title: string;
  descriptions: string[];
  fetchPages?: PageSummary[];
  kind: StepKind;
  hasStart: boolean;
  hasEnd: boolean;
  hasAnswerDelta: boolean;
};

function isStepMessage(message: StreamMessage): message is StepMessage {
  switch (message.type) {
    case "step.start":
    case "step.status":
    case "step.end":
    case "step.fetch.start":
    case "step.fetch.end":
    case "step.answer.start":
    case "step.answer.delta":
    case "step.answer.end":
      return true;
    default:
      return false;
  }
}

function determineStepKind(message: StepMessage): StepKind {
  if (message.type.startsWith("step.fetch")) {
    return "fetch";
  }
  if (message.type.startsWith("step.answer")) {
    return "answer";
  }
  return "generic";
}

function mergeStepKind(current: StepKind, incoming: StepKind): StepKind {
  if (current === incoming) {
    return current;
  }
  if (current === "generic") {
    return incoming;
  }
  if (incoming === "generic") {
    return current;
  }
  return current;
}

function isStartMessage(message: StepMessage): boolean {
  return (
    message.type === "step.start" ||
    message.type === "step.fetch.start" ||
    message.type === "step.answer.start"
  );
}

function isEndMessage(message: StepMessage): boolean {
  return (
    message.type === "step.end" ||
    message.type === "step.fetch.end" ||
    message.type === "step.answer.end"
  );
}

function buildWorkflowSteps(messages: StreamMessage[]): AgentWorkflowStep[] {
  const steps: StepAccumulator[] = [];

  function findOpenStep(title: string): StepAccumulator | undefined {
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      const candidate = steps[index];
      if (candidate.title === title && !candidate.hasEnd) {
        return candidate;
      }
    }
    return undefined;
  }

  function createStep(message: StepMessage): StepAccumulator {
    const step: StepAccumulator = {
      title: message.title,
      descriptions: [],
      kind: determineStepKind(message),
      hasStart: false,
      hasEnd: false,
      hasAnswerDelta: false,
    };
    steps.push(step);
    return step;
  }

  function resolveStep(message: StepMessage): StepAccumulator {
    if (isStartMessage(message)) {
      return createStep(message);
    }
    return findOpenStep(message.title) ?? createStep(message);
  }

  for (const message of messages) {
    if (!isStepMessage(message)) {
      continue;
    }

    const step = resolveStep(message);
    step.kind = mergeStepKind(step.kind, determineStepKind(message));
    step.hasStart = true;

    if (isEndMessage(message)) {
      step.hasEnd = true;
    }

    switch (message.type) {
      case "step.start":
      case "step.status":
      case "step.end":
        if (message.description) {
          step.descriptions.push(message.description);
        }
        break;
      case "step.fetch.start":
      case "step.fetch.end":
        step.fetchPages = message.pages;
        break;
      case "step.answer.start":
        if (message.description) {
          step.descriptions.push(message.description);
        }
        break;
      case "step.answer.delta":
        step.hasAnswerDelta = true;
        break;
      case "step.answer.end":
        break;
    }
  }

  const hasFinalAnswer = messages.some(
    (message): message is AnswerMessage => message.type === "answer"
  );

  if (hasFinalAnswer) {
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      const candidate = steps[index];
      if (candidate.kind === "answer") {
        candidate.hasEnd = true;
        break;
      }
    }
  }

  return steps.map((step) => {
    const status = computeStepStatus(step.hasStart, step.hasEnd);
    const descriptions = uniqueDescriptions(step.descriptions);

    let detail: ReactNode;

    if (step.kind === "fetch") {
      const pages = step.fetchPages ?? [];
      if (pages.length > 0) {
        detail = renderPageList(pages, { variant: "fetch" });
      } else if (status === "active") {
        detail = "Fetching selected sources…";
      } else if (status === "complete") {
        detail = "Fetch completed.";
      } else {
        detail = "Awaiting fetch updates.";
      }
    } else if (step.kind === "answer") {
      const intro = descriptions[0];
      if (status === "complete") {
        detail = "Final response prepared.";
      } else if (step.hasAnswerDelta) {
        detail = intro ?? "Composing response…";
      } else if (intro) {
        detail = intro;
      } else {
        detail = "Preparing response…";
      }
    } else {
      if (descriptions.length > 1) {
        detail = renderDescriptionItems(descriptions);
      } else if (descriptions.length === 1) {
        detail = descriptions[0];
      } else if (status === "active") {
        detail = "In progress…";
      } else if (status === "complete") {
        detail = "Step completed.";
      } else {
        detail = "Awaiting updates.";
      }
    }

    return {
      title: step.title,
      status,
      detail,
    };
  });
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

export function Turn({ turn }: { turn: TurnData }) {
  const { question } = turn;
  const messages = turn.messages ?? [];
  const steps = buildWorkflowSteps(messages);
  const { content: answerContent, references } = extractAnswer(messages);

  return (
    <div className="w-auto space-y-8 py-10 text-zinc-100">
      <section className="overflow-hidden rounded-3xl border border-zinc-800 shadow-xl shadow-black/20">
        <header className="space-y-2 border-b border-zinc-800 p-4 md:p-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Question
          </p>
          <p className="text-lg font-medium leading-7 text-zinc-50">
            {question}
          </p>
        </header>

        <div className="space-y-6 p-4 md:p-6">
          <AgentWorkflowCard steps={steps} />
          <AnswerSection content={answerContent} references={references} />
        </div>
      </section>
    </div>
  );
}
