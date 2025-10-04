export type PageSummary = {
  url: string;
  title?: string | null;
  snippet?: string | null;
  favicon?: string | null;
};

type TurnStartMessage = {
  type: "turn.start";
  conversation_id: string;
};

type SearchStartMessage = {
  type: "search.start";
  query: string;
};

type SearchEndMessage = {
  type: "search.end";
  query: string;
  results: number;
};

type RankStartMessage = {
  type: "rank.start";
};

type RankEndMessage = {
  type: "rank.end";
  pages: PageSummary[];
};

type FetchStartMessage = {
  type: "fetch.start";
  pages: PageSummary[];
};

type FetchEndMessage = {
  type: "fetch.end";
  pages?: PageSummary[] | null;
};

type AnswerDeltaMessage = {
  type: "answer-delta";
  delta: string;
};

type AnswerMessage = {
  type: "answer";
  answer: string;
  citations?: PageSummary[] | null;
};

export type StreamMessage =
  | TurnStartMessage
  | SearchStartMessage
  | SearchEndMessage
  | RankStartMessage
  | RankEndMessage
  | FetchStartMessage
  | FetchEndMessage
  | AnswerDeltaMessage
  | AnswerMessage;

export type ChatStreamEnvelope = {
  event: "message";
  data: StreamMessage;
};

export type ChatErrorEnvelope = {
  event: "error";
  data: {
    error: string;
  };
};

export type ChatDoneEnvelope = {
  event: "end";
  data: {
    message: "[DONE]";
  };
};

export type ChatSseEvent =
  | ChatStreamEnvelope
  | ChatErrorEnvelope
  | ChatDoneEnvelope;

export type TurnData = {
  question: string;
  messages: StreamMessage[];
};
