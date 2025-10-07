import { z } from "zod";

import {
  zChatDoneEnvelope,
  zChatErrorEnvelope,
  zChatStreamEnvelope,
  zPage,
} from "./openapi/zod.gen";

export type PageSummary = z.infer<typeof zPage>;

export type ChatStreamEnvelope = z.infer<typeof zChatStreamEnvelope>;

export type ChatErrorEnvelope = z.infer<typeof zChatErrorEnvelope>;

export type ChatDoneEnvelope = z.infer<typeof zChatDoneEnvelope>;

export type StreamMessage = ChatStreamEnvelope["data"];

export type ChatSseEvent =
  | ChatStreamEnvelope
  | ChatErrorEnvelope
  | ChatDoneEnvelope;

export type TurnData = {
  question: string;
  messages: StreamMessage[];
};
