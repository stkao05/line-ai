import type { PageSummary, TurnData } from "../types";

export const EXAMPLE_PAGES: PageSummary[] = [
  {
    url: "https://doc.rust-lang.org/book/",
    title: "The Rust Programming Language",
    snippet:
      "Foundational chapters on ownership, lifetimes, and error handling.",
    favicon: "https://doc.rust-lang.org/favicon.ico",
  },
  {
    url: "https://github.com/rust-lang/rustlings",
    title: "Rustlings Exercises",
    snippet:
      "Bite-sized tasks that drill the borrow checker and pattern matching.",
    favicon: "https://avatars.githubusercontent.com/u/5430905?s=200&v=4",
  },
  {
    url: "https://rust-by-example.github.io/",
    title: "Rust by Example",
    snippet:
      "Annotated snippets for quick translation from JavaScript concepts.",
    favicon: "https://rust-by-example.github.io/favicon.ico",
  },
];

export const EXAMPLE_TURN: TurnData = {
  question:
    "What is the fastest way to get up to speed with Rust if I already write a lot of JavaScript?",
  messages: [
    {
      type: "turn.start",
      conversation_id: "example-turn",
    },
    {
      type: "step.start",
      title: "Planning the appropriate route",
      description: "Evaluating best workflow for this request.",
    },
    {
      type: "step.end",
      title: "Planning the appropriate route",
      description:
        "Deep dive research selected – gathering sources for a comprehensive response.",
    },
    {
      type: "step.start",
      title: "Running web search",
      description: "Searching for \"fastest way to learn rust for javascript developers\".",
    },
    {
      type: "step.status",
      title: "Running web search",
      description: "Figuring out appropriate search queries...",
    },
    {
      type: "step.status",
      title: "Running web search",
      description:
        "Searching with \"fastest way to learn rust for javascript developers\".",
    },
    {
      type: "step.end",
      title: "Running web search",
      description: "Found 18 candidates for \"fastest way to learn rust for javascript developers\".",
    },
    {
      type: "step.start",
      title: "Ranking candidate sources",
      description: "Prioritizing pages to review in depth.",
    },
    {
      type: "step.end",
      title: "Ranking candidate sources",
      description: "Selected 3 pages for deeper research.",
    },
    {
      type: "step.fetch.start",
      title: "Fetching supporting details",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "step.fetch.end",
      title: "Fetching supporting details",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "step.answer.start",
      title: "Answering the question",
      description: "Synthesizing findings from external research.",
    },
    {
      type: "step.answer.delta",
      title: "Answering the question",
      delta:
        "Rust rewards learning by building. Start with a concise primer on ownership and borrowing, then move directly into shipping a small CLI where you can feel the compiler guiding you.",
    },
    {
      type: "step.answer.end",
      title: "Answering the question",
    },
    {
      type: "answer",
      answer:
        "Rust rewards learning by building. Start with a concise primer on ownership and borrowing, then move directly into shipping a small CLI where you can feel the compiler guiding you.",
      citations: EXAMPLE_PAGES,
    },
  ],
};
