from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

from crewai import Agent, Crew, Process, Task

try:  # crewai<=0.43 re-exports OpenAI; newer releases rely on generic LLM
    from crewai.llm import OpenAI as CrewOpenAI
except ImportError:  # pragma: no cover - compatibility with newer crewai versions
    from crewai.llm import LLM as CrewOpenAI
from pydantic import BaseModel, Field
from tools import google_search

try:  # CrewAI re-exports BaseTool from langchain
    from crewai.tools.base_tool import BaseTool
except ModuleNotFoundError:  # pragma: no cover - fallback for older versions
    from langchain.tools.base import BaseTool


class GoogleSearchInput(BaseModel):
    query: str = Field(..., description="Search query to execute.")
    num_results: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Override for how many search results to fetch (defaults to tool configuration).",
    )
    max_chars: Optional[int] = Field(
        default=None,
        ge=128,
        le=4096,
        description="Override for how many characters of page content to keep per result.",
    )


class GoogleSearchTool(BaseTool):
    """CrewAI-compatible wrapper around our async Google search helper."""

    name = "google_search"
    description = "Execute a Google search via the internal async helper and return enriched results with snippets."
    args_schema = GoogleSearchInput

    def __init__(self, *, num_results: int = 5, max_chars: int = 1500) -> None:
        super().__init__()
        self._default_results = num_results
        self._default_chars = max_chars

    def _run(
        self,
        query: str,
        num_results: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> list[dict[str, str]]:
        return _consume_async(
            google_search(
                query=query,
                num_results=num_results or self._default_results,
                max_chars=max_chars or self._default_chars,
            )
        )

    async def _arun(
        self,
        query: str,
        num_results: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> list[dict[str, str]]:
        return await google_search(
            query=query,
            num_results=num_results or self._default_results,
            max_chars=max_chars or self._default_chars,
        )


@dataclass(slots=True)
class ResearchCrewConfig:
    """Configuration knobs for the research crew."""

    num_results: int = 5
    max_chars: int = 1500
    verbose: bool = False
    model: str = "gpt-4o-mini"
    temperature: float = 0.2


def build_research_crew(
    *,
    llm: Optional[Any] = None,
    config: Optional[ResearchCrewConfig] = None,
) -> Crew:
    """Create a sequential crew with planning, searching, and writing agents."""

    cfg = config or ResearchCrewConfig()
    shared_kwargs = {"verbose": cfg.verbose}
    resolved_llm = llm or _build_default_openai_llm(cfg)
    if resolved_llm is not None:
        shared_kwargs["llm"] = resolved_llm

    planner = Agent(
        role="Planning Strategist",
        goal="Break down the user's question into a short, actionable research plan.",
        backstory=(
            "You are a meticulous project planner who excels at transforming messy ask into"
            " clear, ordered steps that other agents can execute."
        ),
        allow_delegation=False,
        **shared_kwargs,
    )

    searcher = Agent(
        role="Research Specialist",
        goal="Run targeted web searches to gather evidence that satisfies the research plan.",
        backstory=(
            "You are an investigative researcher. You know how to craft focused queries and"
            " summarise the key findings relevant to the task at hand."
        ),
        tools=[GoogleSearchTool(num_results=cfg.num_results, max_chars=cfg.max_chars)],
        allow_delegation=False,
        **shared_kwargs,
    )

    writer = Agent(
        role="Writing Expert",
        goal="Synthesize the research into a clear, reference-backed answer for the user.",
        backstory=(
            "You are an experienced technical writer who can explain complex topics in a"
            " concise and trustworthy way."
        ),
        allow_delegation=False,
        **shared_kwargs,
    )

    planning_task = Task(
        description=(
            "Understand the user's request `{question}` and produce a concise plan consisting of"
            " 3-5 ordered steps that the research specialist can follow."
        ),
        expected_output="A numbered list of concrete research steps, each with a short rationale.",
        agent=planner,
    )

    research_task = Task(
        description=(
            "Execute the previously defined plan to collect the facts needed to answer `{question}`."
            " For each step in the plan, run targeted searches and capture the strongest evidence."
            " Include citations with URLs for every fact you keep."
        ),
        expected_output=(
            "A bullet list grouped by plan step, containing the key findings plus source URLs."
        ),
        agent=searcher,
        context=[planning_task],
    )

    writing_task = Task(
        description=(
            "Draft the final response for `{question}` based on the evidence above."
            " Present a coherent answer that references the plan and research findings."
            " Incorporate citations inline or as end notes."
        ),
        expected_output="A well-structured answer with clear sourcing and actionable conclusions.",
        agent=writer,
        context=[planning_task, research_task],
    )

    crew = Crew(
        agents=[planner, searcher, writer],
        tasks=[planning_task, research_task, writing_task],
        process=Process.sequential,
        verbose=cfg.verbose,
    )
    return crew


def run_research_workflow(
    question: str,
    *,
    llm: Optional[Any] = None,
    config: Optional[ResearchCrewConfig] = None,
):
    """Convenience helper to build the crew and kick off the end-to-end workflow."""

    crew = build_research_crew(llm=llm, config=config)
    return crew.kickoff(inputs={"question": question})


def _build_default_openai_llm(cfg: ResearchCrewConfig) -> Any:
    """Instantiate the default OpenAI-backed LLM using environment configuration."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set; provide it or pass an explicit LLM to the builder."
        )

    return CrewOpenAI(model=cfg.model, temperature=cfg.temperature)


def _consume_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()


__all__ = [
    "ResearchCrewConfig",
    "GoogleSearchTool",
    "build_research_crew",
    "run_research_workflow",
    "main",
]


def main() -> None:
    """Run the research workflow with canned inputs for manual testing."""

    question = (
        "Summarise the latest breakthroughs in multimodal LLMs for customer support."
    )
    config = ResearchCrewConfig(
        num_results=3,
        max_chars=1200,
        verbose=True,
        model="gpt-4o-mini",
    )

    result = run_research_workflow(question, config=config)
    print(result)


if __name__ == "__main__":
    main()
