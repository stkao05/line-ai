import os
from typing import AsyncIterator

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import BaseTextChatMessage
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from tools import google_search

openai_api_key = os.getenv("OPENAI_API_KEY")
model_client = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_api_key)


google_search_tool = FunctionTool(
    google_search,
    description="Search Google for information, returns results with a snippet and body content",
)

search_agent = AssistantAgent(
    name="Google_Search_Agent",
    model_client=model_client,
    tools=[google_search_tool],
    description="Search Google for information, returns top 2 results with a snippet and body content",
    system_message="You are a helpful AI assistant. Solve tasks using your tools.",
)

report_agent = AssistantAgent(
    name="Report_Agent",
    model_client=model_client,
    description="Generate a summary report based on the search result",
    system_message="You are a helpful assistant that can generate a comprehensive report on a given topic based on search. When you done with generating the report, reply with TERMINATE.",
)

team = RoundRobinGroupChat([search_agent, report_agent], max_turns=3)


async def ask(question: str) -> AsyncIterator[str]:
    """Stream responses from the agent for the provided question."""

    stream = team.run_stream(task=question)
    async for message in stream:
        if isinstance(message, BaseTextChatMessage):
            if message.source == "user":
                continue
            yield message.to_text()
