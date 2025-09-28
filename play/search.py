from typing import List, Dict
import asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import StructuredMessage
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient

from duckduckgo_search import DDGS

# Define a tool that searches the web for information.
# For simplicity, we will use a mock function here that returns a static string.
# async def web_search(query: str) -> str:
#     """Find information on the web"""
#     return "AutoGen is a programming framework for building multi-agent applications."



async def web_search(query: str, max_results: int = 3) -> List[Dict[str, str]]:
  out: List[Dict[str, str]] = []

  with DDGS() as ddgs:
    for r in ddgs.text(query, max_results=max_results):
      out.append({
        "title": r.get("title", ""),
        "url": r.get("href", r.get("url", "")),
        "snippet": r.get("body", r.get("snippet", "")),
      })

  return out


# Create an agent that uses the OpenAI GPT-4o model.
model_client = OpenAIChatCompletionClient(
    model="gpt-4.1-nano",
    # api_key="YOUR_API_KEY",
)

agent = AssistantAgent(
    name="assistant",
    model_client=model_client,
    tools=[web_search],
    system_message="Use tools to solve tasks.",
)

async def assistant_run_stream() -> None:
    # Option 1: read each message from the stream (as shown in the previous example).
    async for message in agent.run_stream(task="Find information on AutoGen"):
        print(message)

    # Option 2: use Console to print all messages as they appear.
    # await Console(
    #     agent.run_stream(task="Find information on AutoGen"),
    #     output_stats=True,  # Enable stats printing.
    # )

# Use asyncio.run(assistant_run_stream()) when running in a script.
asyncio.run(assistant_run_stream())