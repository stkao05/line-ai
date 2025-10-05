import type { components } from "./api-types";

type Schemas = components["schemas"];

export type PageSummary = Schemas["Page"];

export type StreamMessage = Schemas["ChatStreamEnvelope"]["data"];

export type ChatStreamEnvelope = Schemas["ChatStreamEnvelope"];

export type ChatErrorEnvelope = Schemas["ChatErrorEnvelope"];

export type ChatDoneEnvelope = Schemas["ChatDoneEnvelope"];

export type ChatSseEvent =
  | ChatStreamEnvelope
  | ChatErrorEnvelope
  | ChatDoneEnvelope;

export type TurnData = {
  question: string;
  messages: StreamMessage[];
};
