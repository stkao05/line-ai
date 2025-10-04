"use client";

import { useChat } from "../hooks/useChat";
import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useCallback,
  useState,
} from "react";
import { Turn } from "../components/turn";
import { ChatForm } from "../components/chat-form";

export function Chat() {
  const { turns, status, error, sendMessage } = useChat();
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

  const hasTurns = turns.length > 0;

  return (
    <main className="max-w-[1000px] mx-auto pb-[120px]">
      <div className="space-y-4">
        {hasTurns
          ? turns.map((turn, index) => <Turn key={index} turn={turn} />)
          : <Turn />}
      </div>
      <div className="fixed bottom-4 w-full max-w-[1000px]">
        {error ? (
          <div className="mb-3 rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        ) : null}
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
