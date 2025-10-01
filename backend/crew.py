from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM
from crewai_tools import SerperDevTool

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


@dataclass(slots=True)
class ResearchCrewConfig:
    verbose: bool = False
    model: str = "gpt-4o-mini"


def build_research_crew(
    llm: Optional[Any] = None,
    config: Optional[ResearchCrewConfig] = None,
) -> Crew:
    cfg = config or ResearchCrewConfig()
    shared_kwargs = {
        "verbose": cfg.verbose,
        "llm": LLM(model=cfg.model),
    }

    researcher = Agent(
        role="Research Specialist",
        goal="Run targeted web searches to gather the strongest evidence for the question.",
        backstory=(
            "You are an investigative researcher. You know how to craft focused queries and"
            " summarise the key findings relevant to the task at hand."
        ),
        tools=[SerperDevTool()],
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

    research_task = Task(
        description=(
            "Run targeted web searches to collect the facts needed to answer `{question}`."
            " Capture the strongest evidence and include citations with URLs for every fact you keep."
        ),
        expected_output=("A bullet list of key findings with supporting source URLs."),
        agent=researcher,
    )

    writing_task = Task(
        description=(
            "Draft the final response for `{question}` based on the evidence above."
            " Present a coherent answer that references the research findings."
            " Incorporate citations inline or as end notes."
        ),
        expected_output="A well-structured answer with clear sourcing and actionable conclusions.",
        agent=writer,
        context=[research_task],
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
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
    crew = build_research_crew(llm=llm, config=config)
    return crew.kickoff(inputs={"question": question})


__all__ = [
    "ResearchCrewConfig",
    "build_research_crew",
    "run_research_workflow",
    "main",
]


def main() -> None:
    question = (
        "Summarise the latest breakthroughs in multimodal LLMs for customer support."
    )
    config = ResearchCrewConfig(verbose=True, model="gpt-4o-mini")
    result = run_research_workflow(question, config=config)
    print(result)


if __name__ == "__main__":
    main()
