# %%
import os
from typing import AsyncIterator, List, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import BaseTextChatMessage, StructuredMessage
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from pydantic import BaseModel
from tools import google_search

openai_api_key = os.getenv("OPENAI_API_KEY")
model_client = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_api_key)


class SearchResultItem(BaseModel):
    title: str
    url: str
    favicon: Optional[str] = None
    snippet: str
    detail_summary: str


class SearchResult(BaseModel):
    results: List[SearchResultItem]


SearchResultMessage = StructuredMessage[SearchResult]


google_search_tool = FunctionTool(
    google_search,
    description="Search Google for information",
    strict=True,
)


def create_team():
    search_system_message = """
    You are a **search assistant agent**.  

    - Given a user’s question, generate **one or more precise Google search queries** that are most likely to retrieve high-quality answers.  
    - Use the **Google search tool** to fetch up to **5 candidate pages**.  
    - From those, select the **top 3 most relevant results**.  
    - For each result, return a structured object with the following fields:  
    - `title`: page title  
    - `url`: canonical page URL  
    - `favicon`: site favicon (if available)  
    - `snippet`: a short extract showing relevance  
    - `detail_summary`: a clear, well-organized summary of the page content that contains all necessary details to answer the user’s question. The summary should be comprehensive, but focused on the user’s query.  
    - Ensure results are **ranked by relevance**, not just by order of retrieval.
    """

    search_agent = AssistantAgent(
        name="google_search_agent",
        model_client=model_client,
        tools=[google_search_tool],
        output_content_type=SearchResult,
        description="Search Google for relevant information that could help answering the question",
        system_message=search_system_message,
    )

    report_agent = AssistantAgent(
        name="Report_Agent",
        model_client=model_client,
        description="Generate a summary report based on the search result",
        system_message="You are a helpful assistant that can generate a comprehensive report on a given topic based on search. When you done with generating the report, reply with TERMINATE.",
    )

    team = RoundRobinGroupChat(
        [search_agent, report_agent],
        max_turns=3,
        custom_message_types=[SearchResultMessage],
    )

    return team


async def ask(question: str) -> AsyncIterator[str]:
    """Stream responses from the agent for the provided question."""

    team = create_team()
    stream = team.run_stream(task=question)
    async for message in stream:
        print(message)
        if isinstance(message, BaseTextChatMessage):
            if message.source == "user":
                continue
            yield message.to_text()


# # %%
# import asyncio

# stream = search_agent.run_stream(task="what is the current state of corona virus")
# messages = []
# async for message in stream:
#     messages.append(message)

# print(messages)


# # %%

# from rich import inspect, pretty
# from rich import print as pprint

# pprint(messages[3])


# # %%
