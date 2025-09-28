export type Snowflake = string;
export type ISO8601 = string;

export type SseEvent =
  | "turn.start"
  | "turn.done"
  | "answer.delta"
  | "answer.done"
  | "agent.status";

export interface BaseMeta {
  conversation_id: Snowflake;
  turn_id: Snowflake;
  id: Snowflake;
  ts: ISO8601;
}

export interface TurnStart extends BaseMeta {
  user_message: {
    text: string;
  };
}

export interface TurnDone extends BaseMeta {
  status: "ok" | "error";
}

export interface AnswerDelta extends BaseMeta {
  text: string;
}

export interface AnswerDone extends BaseMeta {
  final_text_hash?: string;
}

export interface AgentStatus extends BaseMeta {
  stage: "planning" | "retrieving" | "writing";
  detail?: string;
}

export type SseMessage =
  | { event: "turn.start"; data: TurnStart }
  | { event: "turn.done"; data: TurnDone }
  | { event: "answer.delta"; data: AnswerDelta }
  | { event: "answer.done"; data: AnswerDone }
  | { event: "agent.status"; data: AgentStatus };

// the message state representation used on the UI

export interface MessageBase {
  conversation_id: string;
  turn_id: Snowflake;
}

export interface UserMessage extends MessageBase {
  type: "user.message";
  content: string;
}

export interface AssistantAnsweringMessage extends MessageBase {
  type: "assistant.message";
  content: string;
}

export interface AgentStatusMessage extends MessageBase {
  type: "agent.status";
  stage: "planning" | "retrieving" | "writing";
  detail?: string;
}

export type ChatMessage = UserMessage | AssistantAnsweringMessage;

export type Message = ChatMessage | AgentStatusMessage;
