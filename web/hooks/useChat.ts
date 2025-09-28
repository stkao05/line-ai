import { useCallback, useEffect, useRef, useState } from "react";
import { Message } from "../app/types";

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

    const params = new URLSearchParams({ question });
    const streamUrl = `${process.env.NEXT_PUBLIC_CHAT_BASE_URL}/chat?${params.toString()}`;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      content: question,
      from: "user",
    };
    const assistantMessageId = crypto.randomUUID();

    setMessages((previous) => [
      ...previous,
      userMessage,
      { id: assistantMessageId, content: "", from: "llm" },
    ]);
    setStatus("streaming");
    setError(null);

    const stream = new EventSource(streamUrl);
    streamRef.current = stream;

    const updateAssistantMessage = (transform: (content: string) => string) => {
      setMessages((previous) =>
        previous.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: transform(message.content) }
            : message
        )
      );
    };

    function cleanup(nextStatus: ChatStatus) {
      stream.removeEventListener("message", handleMessage);
      stream.removeEventListener("end", handleEnd);
      stream.removeEventListener("error", handleError);
      stream.close();
      if (streamRef.current === stream) {
        streamRef.current = null;
      }
      cleanupRef.current = null;
      setStatus(nextStatus);
    }

    function handleMessage(event: MessageEvent) {
      try {
        const payload = JSON.parse(event.data) as { message?: string };
        if (!payload.message) {
          return;
        }
        updateAssistantMessage((current) => current + payload.message);
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
          updateAssistantMessage((current) => current + payload.message);
        }
      } catch (parseError) {
        console.error("Failed to parse SSE end message", parseError);
        setError("Failed to parse SSE end message");
        cleanup("error");
        return;
      }
      cleanup("ready");
    }

    function handleError(event: MessageEvent) {
      console.error("SSE error", event);
      setError("Streaming connection failed");
      cleanup("error");
    }

    cleanupRef.current = cleanup;

    stream.addEventListener("message", handleMessage);
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
