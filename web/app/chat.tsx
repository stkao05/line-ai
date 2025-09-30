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
import { SendHorizonal } from "lucide-react";

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
      <div>
        {messages.map((message) => {
          const key = `${message.turn_id}:${message.type}`;

          if (message.type === "agent.status") {
            return (
              <div key={key} className="text-sm text-zinc-400">
                <span className="uppercase tracking-wide">{message.stage}</span>
                {message.detail ? <span>: {message.detail}</span> : null}
              </div>
            );
          }

          const author = message.type === "user.message" ? "You" : "Assistant";
          return (
            <div key={key}>
              <div>
                <span className="font-semibold">{author}:</span>{" "}
                {message.content}
              </div>
            </div>
          );
        })}
        {error ? <div className="text-red-400">{error}</div> : null}
      </div>
      <div className="fixed bottom-4 w-full max-w-[1000px]">
        <form
          className="flex max-w-[1000px] items-center gap-3 rounded-3xl border border-zinc-800 bg-zinc-950/60 p-4 shadow-xl shadow-black/20"
          onSubmit={handleSubmit}
        >
          <textarea
            className="w-full resize-none bg-transparent text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
            name="message"
            placeholder="Message"
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleInputKeyDown}
            autoFocus
            disabled={status === "streaming"}
          />
          <button
            type="submit"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500 text-white transition-colors hover:bg-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
            disabled={status === "streaming" || !input.trim()}
            aria-label={status === "streaming" ? "Sending" : "Send message"}
          >
            <SendHorizonal size={16} />
          </button>
        </form>
      </div>
    </main>
  );
}
