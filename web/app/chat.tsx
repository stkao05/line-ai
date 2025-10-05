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

const SHOW_MOCK_TURN = false;
const SUGGESTED_QUESTIONS = [
  "What's new with LINE this year?",
  "Why is sky blue?",
  "Could you write topological sort in Python?",
  "How can I evaluate model quality when prototyping with AI agent?",
];

export function Chat() {
  const { turns, status, error, sendMessage } = useChat();
  const [input, setInput] = useState("");

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
  const shouldShowMockTurn = SHOW_MOCK_TURN && !hasTurns;
  const shouldShowWelcomeScreen = !hasTurns && !shouldShowMockTurn;

  const handleSuggestionSelect = useCallback(
    (suggestion: string) => {
      // Auto-submit when a suggestion is clicked
      if (status === "streaming") {
        return;
      }
      sendMessage({ text: suggestion });
      setInput("");
    },
    [sendMessage, status]
  );

  return (
    <main className="max-w-[1000px] mx-auto pb-[120px]">
      <div className="space-y-4">
        {hasTurns ? (
          turns.map((turn, index) => <Turn key={index} turn={turn} />)
        ) : shouldShowMockTurn ? (
          <Turn />
        ) : shouldShowWelcomeScreen ? (
          <WelcomeScreen
            suggestions={SUGGESTED_QUESTIONS}
            onSelect={handleSuggestionSelect}
          />
        ) : null}
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

type WelcomeScreenProps = {
  suggestions: readonly string[];
  onSelect: (value: string) => void;
};

function WelcomeScreen({ suggestions, onSelect }: WelcomeScreenProps) {
  return (
    <section className="mt-16  text-zinc-100">
      <div className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          Welcome
        </p>
        <h1 className="text-3xl font-semibold text-zinc-50">
          How can LINE AI help you today?
        </h1>
        <p className="text-sm text-zinc-400">
          Pick a suggested question to jump in or type your own prompt below.
        </p>
      </div>
      <div className="mt-8 grid gap-3 md:grid-cols-2">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4 text-left text-sm text-zinc-200 transition hover:border-emerald-400/60 hover:bg-emerald-500/10 hover:text-emerald-100 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-zinc-950"
            onClick={() => onSelect(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </section>
  );
}
