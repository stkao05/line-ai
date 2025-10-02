"use client";

import { useChat } from "../hooks/useChat";
import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useCallback,
  useState,
} from "react";
import { Turn } from "./turn";
import { ChatForm } from "./chat-form";

export function Chat() {
  const { messages, status, error, sendMessage } = useChat();
  const [input, setInput] = useState("what is today weather in taipai");

  const handleInputChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();

      const question = input.trim();
      if (!question || status === "streaming") {
        return;
      }

      sendMessage({ text: question });
      setInput("");
    },
    [input, sendMessage, status]
  );

  return (
    <main className="max-w-[1000px] mx-auto pb-[100px]">
      <div>
        <Turn />
      </div>
      <div className="fixed bottom-4 w-full max-w-[1000px]">
        <ChatForm
          status={status}
          value={input}
          onSubmit={handleSubmit}
          onChange={handleInputChange}
          onKeyDown={handleInputKeyDown}
        />
      </div>
    </main>
  );
}
