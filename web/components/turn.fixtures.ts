import type { PageSummary, TurnData } from "./types";

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
      type: "search.start",
      query: "fastest way to learn rust for javascript developers",
    },
    {
      type: "search.end",
      query: "fastest way to learn rust for javascript developers",
      results: 18,
    },
    {
      type: "rank.start",
    },
    {
      type: "rank.end",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "fetch.start",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "fetch.end",
      pages: EXAMPLE_PAGES,
    },
    {
      type: "answer-delta",
      delta:
        "Rust rewards learning by building. Start with a concise primer on ownership and borrowing, then move directly into shipping a small CLI where you can feel the compiler guiding you.",
    },
  ],
};
