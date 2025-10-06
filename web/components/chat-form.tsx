"use client";

import { ChangeEvent, FormEvent, KeyboardEvent } from "react";
import { SendHorizonal } from "lucide-react";

type ChatFormProps = {
  status: "ready" | "streaming" | "error";
  value: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
};

export function ChatForm({
  status,
  value,
  onSubmit,
  onChange,
  onKeyDown,
}: ChatFormProps) {
  return (
    <form
      className="flex max-w-[1000px] items-center gap-3 rounded-full border border-zinc-800 bg-zinc-900 py-4 px-6 shadow-xl shadow-black/20"
      onSubmit={onSubmit}
    >
      <textarea
        className="w-full resize-none bg-transparent text-zinc-100 placeholder:text-zinc-500 focus:outline-none disabled:cursor-not-allowed"
        name="message"
        placeholder={status === "streaming" ? "Answering..." : "Ask anything"}
        rows={1}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        autoFocus
        disabled={status === "streaming"}
      />
      <button
        type="submit"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-line text-white transition-colors hover:bg-line-400 focus:outline-none focus:ring-2 focus:ring-line-400 focus:ring-offset-2 focus:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400 disabled:cursor-not-allowed"
        disabled={status === "streaming" || !value.trim()}
        aria-label={status === "streaming" ? "Sending" : "Send message"}
      >
        <SendHorizonal size={16} />
      </button>
    </form>
  );
}
