"use client";

import { useChat } from "../hooks/useChat";
import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useCallback,
  useState,
} from "react";

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
    <main className="max-w-[1200px] mx-auto px-4">
      <div>
        {messages.map((message) => (
          <div key={message.id}>
            <div>{message.content}</div>
          </div>
        ))}
        {error ? <div className="text-red-400">{error}</div> : null}
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
          disabled={status === "streaming"}
        />
        <button
          type="submit"
          disabled={status === "streaming" || !input.trim()}
        >
          {status === "streaming" ? "Sending..." : "Send"}
        </button>
      </form>
    </main>
  );
}
