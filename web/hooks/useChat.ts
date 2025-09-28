import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentStatusMessage,
  AssistantAnsweringMessage,
  Message,
  SseEvent,
  SseMessage,
  UserMessage,
} from "../app/types";

type ChatStatus = "ready" | "streaming" | "error";

type UseChatReturn = {
  messages: Message[];
  status: ChatStatus;
  error: string | null;
  sendMessage: (args: { text: string }) => void;
  cancel: () => void;
};

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<ChatStatus>("ready");
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<EventSource | null>(null);
  const cleanupRef = useRef<((nextStatus: ChatStatus) => void) | null>(null);

  const cancel = useCallback(() => {
    cleanupRef.current?.("ready");
    cleanupRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);

  const sendMessage = ({ text }: { text: string }) => {
    const question = text.trim();
    if (!question || streamRef.current) {
      return;
    }

    const params = new URLSearchParams({ user_message: question });
    const streamUrl = `${process.env.NEXT_PUBLIC_CHAT_BASE_URL}/chat?${params.toString()}`;

    const clientTurnId = crypto.randomUUID();
    const placeholderUserMessage: UserMessage = {
      conversation_id: clientTurnId,
      turn_id: clientTurnId,
      type: "user.message",
      content: question,
    };
    const placeholderAssistantMessage: AssistantAnsweringMessage = {
      conversation_id: clientTurnId,
      turn_id: clientTurnId,
      type: "assistant.message",
      content: "",
    };

    setMessages((previous) => [
      ...previous,
      placeholderUserMessage,
      placeholderAssistantMessage,
    ]);
    setStatus("streaming");
    setError(null);

    const stream = new EventSource(streamUrl);
    streamRef.current = stream;

    function cleanup(nextStatus: ChatStatus) {
      stream.removeEventListener("message", handleSsePayload);
      stream.removeEventListener("end", handleEnd);
      stream.removeEventListener("error", handleError);
      stream.close();
      if (streamRef.current === stream) {
        streamRef.current = null;
      }
      cleanupRef.current = null;
      setStatus(nextStatus);
    }

    function ensureKnownEvent(value: unknown): value is SseEvent {
      return (
        value === "turn.start" ||
        value === "turn.done" ||
        value === "answer.delta" ||
        value === "answer.done" ||
        value === "agent.status"
      );
    }

    function applyTurnStart(
      payload: Extract<SseMessage, { event: "turn.start" }>
    ) {
      const {
        data: {
          conversation_id: conversationId,
          turn_id: turnId,
          user_message: { text: userText },
        },
      } = payload;

      setMessages((previous) =>
        previous.map((message) => {
          if (message.turn_id !== clientTurnId) {
            return message;
          }

          if (message.type === "user.message") {
            return {
              ...message,
              conversation_id: conversationId,
              turn_id: turnId,
              content: userText,
            };
          }

          if (message.type === "assistant.message") {
            return {
              ...message,
              conversation_id: conversationId,
              turn_id: turnId,
            };
          }

          return message;
        })
      );
    }

    function applyAnswerDelta(
      payload: Extract<SseMessage, { event: "answer.delta" }>
    ) {
      const {
        data: { conversation_id: conversationId, turn_id: turnId, text },
      } = payload;

      setMessages((previous) => {
        let assistantFound = false;
        const updated = previous.map((message) => {
          if (
            message.type === "assistant.message" &&
            message.conversation_id === conversationId &&
            message.turn_id === turnId
          ) {
            assistantFound = true;
            return {
              ...message,
              content: message.content + text,
            };
          }
          return message;
        });

        if (assistantFound) {
          return updated;
        }

        return [
          ...updated,
          {
            conversation_id: conversationId,
            turn_id: turnId,
            type: "assistant.message",
            content: text,
          },
        ];
      });
    }

    function applyAnswerDone(
      payload: Extract<SseMessage, { event: "answer.done" }>
    ) {
      if (!payload.data.final_text_hash) {
        return;
      }

      const {
        data: { conversation_id: conversationId, turn_id: turnId },
      } = payload;

      setMessages((previous) =>
        previous.map((message) => {
          if (
            message.type === "assistant.message" &&
            message.conversation_id === conversationId &&
            message.turn_id === turnId
          ) {
            return {
              ...message,
            };
          }
          return message;
        })
      );
    }

    function applyAgentStatus(
      payload: Extract<SseMessage, { event: "agent.status" }>
    ) {
      const {
        data: {
          conversation_id: conversationId,
          turn_id: turnId,
          stage,
          detail,
        },
      } = payload;

      const statusMessage: AgentStatusMessage = {
        conversation_id: conversationId,
        turn_id: turnId,
        type: "agent.status",
        stage,
        detail,
      };

      setMessages((previous) => {
        const existingIndex = previous.findIndex(
          (message) =>
            message.type === "agent.status" &&
            message.conversation_id === conversationId &&
            message.turn_id === turnId
        );

        if (existingIndex === -1) {
          return [...previous, statusMessage];
        }

        const updated = [...previous];
        updated[existingIndex] = statusMessage;
        return updated;
      });
    }

    function applyTurnDone(
      payload: Extract<SseMessage, { event: "turn.done" }>
    ) {
      const {
        data: { status: turnStatus },
      } = payload;

      if (turnStatus === "ok") {
        cleanup("ready");
        return;
      }

      setError("Turn ended with an error");
      cleanup("error");
    }

    function handleSsePayload(event: MessageEvent) {
      try {
        const parsed = JSON.parse(event.data) as Partial<SseMessage>;

        if (!parsed || typeof parsed !== "object") {
          return;
        }

        if (!ensureKnownEvent(parsed.event)) {
          console.warn("Unknown SSE event", parsed);
          return;
        }

        if (
          !("data" in parsed) ||
          typeof parsed.data !== "object" ||
          parsed.data === null
        ) {
          console.warn("Malformed SSE payload", parsed);
          return;
        }

        const payload = parsed as SseMessage;

        switch (payload.event) {
          case "turn.start":
            applyTurnStart(payload);
            break;
          case "answer.delta":
            applyAnswerDelta(payload);
            break;
          case "answer.done":
            applyAnswerDone(payload);
            break;
          case "agent.status":
            applyAgentStatus(payload);
            break;
          case "turn.done":
            applyTurnDone(payload);
            break;
          default:
            console.warn("Unhandled SSE event", payload.event);
            break;
        }
      } catch (parseError) {
        console.error("Failed to parse SSE message", parseError);
        setError("Failed to parse SSE message");
        cleanup("error");
      }
    }

    function handleEnd(event: MessageEvent) {
      try {
        const payload = JSON.parse(event.data) as { message?: string };
        if (payload.message && payload.message !== "[DONE]") {
          console.warn("Unexpected end payload", payload);
        }
      } catch (parseError) {
        console.error("Failed to parse SSE end message", parseError);
        setError("Failed to parse SSE end message");
        cleanup("error");
        return;
      }
      cleanup("ready");
    }

    function handleError(event: Event) {
      console.error("SSE error", event);

      if ("data" in event && typeof (event as MessageEvent).data === "string") {
        try {
          const payload = JSON.parse((event as MessageEvent).data) as {
            error?: string;
          };
          if (payload.error) {
            setError(payload.error);
            cleanup("error");
            return;
          }
        } catch (parseError) {
          console.error("Failed to parse SSE error payload", parseError);
        }
      }

      setError("Streaming connection failed");
      cleanup("error");
    }

    cleanupRef.current = cleanup;

    stream.addEventListener("message", handleSsePayload);
    stream.addEventListener("end", handleEnd);
    stream.addEventListener("error", handleError);
  };

  return {
    messages,
    status,
    error,
    sendMessage,
    cancel,
  };
}
