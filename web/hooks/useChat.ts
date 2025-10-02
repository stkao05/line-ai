import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatDoneEnvelope,
  ChatErrorEnvelope,
  ChatStreamEnvelope,
  StreamMessage,
  TurnData,
} from "../app/types";

type ChatStatus = "ready" | "streaming" | "error";

type UseChatReturn = {
  turn: TurnData | null;
  status: ChatStatus;
  error: string | null;
  sendMessage: (args: { text: string }) => void;
  cancel: () => void;
};

function isStreamMessage(value: unknown): value is StreamMessage {
  if (!value || typeof value !== "object") {
    return false;
  }

  const { type } = value as { type?: unknown };
  return (
    type === "search.start" ||
    type === "search.end" ||
    type === "rank.start" ||
    type === "rank.end" ||
    type === "fetch.start" ||
    type === "fetch.end" ||
    type === "answer-delta" ||
    type === "answer"
  );
}

export function useChat(): UseChatReturn {
  const [turn, setTurn] = useState<TurnData | null>(null);
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
    const streamUrl = `${baseUrl}/chat?${params.toString()}`;

    const stream = new EventSource(streamUrl);
    streamRef.current = stream;

    setTurn({ question, messages: [] });
    setStatus("streaming");
    setError(null);

    function cleanup(nextStatus: ChatStatus) {
      stream.removeEventListener("message", handleStreamMessage);
      stream.removeEventListener("end", handleStreamEnd);
      stream.removeEventListener("error", handleStreamError);
      stream.close();
      if (streamRef.current === stream) {
        streamRef.current = null;
      }
      cleanupRef.current = null;
      setStatus(nextStatus);
    }

    function appendMessage(message: StreamMessage) {
      setTurn((previous) => {
        if (!previous) {
          return { question, messages: [message] };
        }

        return {
          ...previous,
          messages: [...previous.messages, message],
        };
      });
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

    cleanupRef.current = cleanup;

    stream.addEventListener("message", handleStreamMessage);
    stream.addEventListener("end", handleStreamEnd);
    stream.addEventListener("error", handleStreamError);
  }, []);

  return {
    turn,
    status,
    error,
    sendMessage,
    cancel,
  };
}
