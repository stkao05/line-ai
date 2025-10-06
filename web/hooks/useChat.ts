import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatDoneEnvelope,
  ChatErrorEnvelope,
  ChatStreamEnvelope,
  StreamMessage,
  TurnData,
} from "../types";

type ChatStatus = "ready" | "streaming" | "error";

type UseChatReturn = {
  turns: TurnData[];
  status: ChatStatus;
  error: string | null;
  sendMessage: (args: { text: string }) => void;
  cancel: () => void;
};

type CreateChatStreamOptions = {
  url: string;
  appendMessage: (message: StreamMessage) => void;
  setError: (message: string) => void;
  setStatus: (status: ChatStatus) => void;
  onCleanup: (nextStatus: ChatStatus) => void;
};

type ChatStreamController = {
  stream: EventSource;
  cleanup: (nextStatus: ChatStatus) => void;
};

function createChatStream({
  url,
  appendMessage,
  setError,
  setStatus,
  onCleanup,
}: CreateChatStreamOptions): ChatStreamController {
  const stream = new EventSource(url);

  function cleanup(nextStatus: ChatStatus) {
    stream.removeEventListener("message", handleStreamMessage);
    stream.removeEventListener("end", handleStreamEnd);
    stream.removeEventListener("error", handleStreamError);
    stream.close();
    setStatus(nextStatus);
    onCleanup(nextStatus);
  }

  function handleStreamMessage(event: MessageEvent) {
    try {
      const parsed = JSON.parse(event.data) as Partial<ChatStreamEnvelope>;

      if (!parsed || parsed.event !== "message") {
        return;
      }

      if (!parsed.data) {
        console.warn("Stream event missing data payload", parsed);
        return;
      }

      if (!isStreamMessage(parsed.data)) {
        console.warn("Unknown stream message type", parsed.data);
        return;
      }

      appendMessage(parsed.data);
    } catch (streamError) {
      console.error("Failed to parse stream message", streamError);
      setError("Failed to parse stream message");
      cleanup("error");
    }
  }

  function handleStreamEnd(event: MessageEvent) {
    try {
      const payload = JSON.parse(event.data) as ChatDoneEnvelope["data"];
      if (payload.message && payload.message !== "[DONE]") {
        console.warn("Unexpected stream end payload", payload);
      }
    } catch (parseError) {
      console.error("Failed to parse stream end payload", parseError);
      setError("Failed to parse stream end payload");
      cleanup("error");
      return;
    }

    cleanup("ready");
  }

  function handleStreamError(event: Event) {
    console.error("Stream error", event);

    if (
      "data" in event &&
      typeof (event as MessageEvent).data === "string" &&
      (event as MessageEvent).data
    ) {
      try {
        const payload = JSON.parse(
          (event as MessageEvent).data
        ) as ChatErrorEnvelope["data"];
        if (payload.error) {
          setError(payload.error);
          cleanup("error");
          return;
        }
      } catch (parseError) {
        console.error("Failed to parse stream error payload", parseError);
      }
    }

    setError("Streaming connection failed");
    cleanup("error");
  }

  stream.addEventListener("message", handleStreamMessage);
  stream.addEventListener("end", handleStreamEnd);
  stream.addEventListener("error", handleStreamError);

  return { stream, cleanup };
}

function isStreamMessage(value: unknown): value is StreamMessage {
  if (!value || typeof value !== "object") {
    return false;
  }

  const { type } = value as { type?: unknown };
  return (
    type === "turn.start" ||
    type === "step.start" ||
    type === "step.status" ||
    type === "step.end" ||
    type === "step.fetch.start" ||
    type === "step.fetch.end" ||
    type === "step.answer.start" ||
    type === "step.answer.delta" ||
    type === "step.answer.end" ||
    type === "answer"
  );
}

export function useChat(): UseChatReturn {
  const [turns, setTurns] = useState<TurnData[]>([]);
  const [status, setStatus] = useState<ChatStatus>("ready");
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<EventSource | null>(null);
  const cleanupRef = useRef<((nextStatus: ChatStatus) => void) | null>(null);
  const activeTurnIndexRef = useRef<number | null>(null);
  const conversationIdRef = useRef<string | null>(null);

  const cancel = useCallback(() => {
    cleanupRef.current?.("ready");
    cleanupRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);

  const sendMessage = useCallback(({ text }: { text: string }) => {
    const question = text.trim();
    if (!question || streamRef.current) {
      return;
    }

    const baseUrl = process.env.NEXT_PUBLIC_CHAT_BASE_URL;
    if (!baseUrl) {
      setError("Chat service URL is not configured");
      return;
    }

    const params = new URLSearchParams({ user_message: question });
    if (conversationIdRef.current) {
      params.set("conversation_id", conversationIdRef.current);
    }
    const streamUrl = `${baseUrl}/chat?${params.toString()}`;

    setTurns((previous) => {
      const next = [...previous, { question, messages: [] }];
      activeTurnIndexRef.current = next.length - 1;
      return next;
    });
    setStatus("streaming");
    setError(null);

    const appendMessage = (message: StreamMessage) => {
      const turnIndex = activeTurnIndexRef.current;
      if (turnIndex === null) {
        return;
      }

      if (message.type === "turn.start") {
        conversationIdRef.current = message.conversation_id;
      }

      setTurns((previous) => {
        if (turnIndex < 0 || turnIndex >= previous.length) {
          return previous;
        }

        const nextTurns = [...previous];
        const currentTurn = nextTurns[turnIndex];
        nextTurns[turnIndex] = {
          ...currentTurn,
          messages: [...currentTurn.messages, message],
        };
        return nextTurns;
      });
    };

    let cleanupFn: ((nextStatus: ChatStatus) => void) | null = null;
    let cleanupStream: EventSource | null = null;

    const { stream, cleanup } = createChatStream({
      url: streamUrl,
      appendMessage,
      setError: (message) => setError(message),
      setStatus,
      onCleanup: (nextStatus) => {
        void nextStatus;
        if (streamRef.current === cleanupStream) {
          streamRef.current = null;
        }
        if (cleanupRef.current === cleanupFn) {
          cleanupRef.current = null;
        }
        activeTurnIndexRef.current = null;
      },
    });

    cleanupFn = cleanup;
    cleanupStream = stream;

    streamRef.current = stream;
    cleanupRef.current = cleanup;
  }, []);

  return {
    turns,
    status,
    error,
    sendMessage,
    cancel,
  };
}
