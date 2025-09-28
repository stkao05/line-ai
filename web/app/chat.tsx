"use client";

import { Message } from "./types";
import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useEffect,
  useState,
} from "react";

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("what is today weather in taipai");
  const [activeStream, setActiveStream] = useState<EventSource | null>(null);

  useEffect(() => {
    return () => {
      activeStream?.close();
    };
  }, [activeStream]);

  const handleInputChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // TODO: need to check if this is best practice...maybe should use input
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const question = input.trim();
    if (!question || activeStream) {
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      content: question,
      from: "user",
    };
    const assistantMessageId = crypto.randomUUID();

    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantMessageId, content: "", from: "llm" },
    ]);
    setInput("");

    const stream = new EventSource(
      `${process.env.NEXT_PUBLIC_CHAT_BASE_URL}/chat?question=${encodeURIComponent(question)}`
    );
    setActiveStream(stream);

    const updateAssistantMessage = (transform: (content: string) => string) => {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: transform(message.content) }
            : message
        )
      );
    };

    const closeStream = () => {
      stream.close();
      setActiveStream((current) => (current === stream ? null : current));
    };

    stream.addEventListener("message", (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { message?: string };
        if (!payload.message) {
          return;
        }
        updateAssistantMessage((current) => current + payload.message);
      } catch (error) {
        console.error("Failed to parse SSE message", error);
      }
    });

    stream.addEventListener("end", (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { message?: string };
        if (payload.message && payload.message !== "[DONE]") {
          updateAssistantMessage((current) => current + payload.message);
        }
      } catch (error) {
        console.error("Failed to parse SSE end message", error);
      } finally {
        closeStream();
      }
    });

    stream.addEventListener("error", (event: MessageEvent) => {
      console.error("SSE error", event);
      closeStream();
    });
  };

  return (
    <main className="max-w-[1200px] mx-auto px-4">
      <div>
        {messages.map((message) => (
          <div key={message.id}>
            <div>{message.content}</div>
          </div>
        ))}
      </div>
      <form
        className="fixed max-w-[1000px] mx-auto bottom-0 left-0 right-0 p-4"
        onSubmit={handleSubmit}
      >
        <textarea
          className="bg-zinc-800 w-full border-1 border-zinc-900 rounded-2xl p-8 focus:outline-none"
          name="message"
          placeholder="Message"
          rows={1}
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleInputKeyDown}
          autoFocus
          disabled={Boolean(activeStream)}
        />
        <button type="submit" disabled={Boolean(activeStream) || !input.trim()}>
          {activeStream ? "Sending..." : "Send"}
        </button>
      </form>
    </main>
  );
}
