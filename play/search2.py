import asyncio
import os
from typing import Annotated

import autogen_agentchat.agents as agents
import autogen_agentchat.messages as messages
from autogen_agentchat.teams import RoundRobinTeam
from autogen_core import Image  # For multi-modal if needed
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.tools import FunctionTool, ToolCallRequestEvent
from duckduckgo_search import DDGS

# Configure the LLM client (e.g., OpenAI)
model_client = OpenAIChatCompletionClient(
    model="gpt-4o-mini",  # Or "ollama/llama3" with Ollama extension
    api_key=os.getenv("OPENAI_API_KEY"),
)

# Define the web search tool
async def web_search(query: Annotated[str, "The search query"]) -> str:
    """Perform a web search to retrieve up-to-date information for answering queries."""
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)
            formatted_results = "\n".join(
                [f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n" for r in results]
            )
            return formatted_results or "No results found."
    except Exception as e:
        return f"Error during web search: {str(e)}"

# Create the FunctionTool (auto-generates JSON schema for LLM)
web_search_tool = FunctionTool(
    web_search,
    name="web_search",
    description="Search the web for current information when you need facts beyond your knowledge.",
)

# Create the AssistantAgent (handles queries, decides tool use)
assistant = agents.AssistantAgent(
    name="QAAgent",
    model_client=model_client,
    system_message="You are a helpful Q&A assistant like Perplexity. Answer questions concisely and accurately. Use the web_search tool for up-to-date info. Cite sources from results. Structure responses clearly.",
    tools=[web_search_tool],  # Register tool here
)

# Create the UserProxyAgent (handles user input)
user_proxy = agents.UserProxyAgent(
    name="User",
    model_client=None,  # No LLM; just proxies user input
    human_input_mode="ALWAYS",  # Prompts user for input each time
    is_termination_msg=lambda msg: msg.get("content", "").lower() == "quit",
)

# Create a simple team for collaboration (optional; can use direct chat)
team = RoundRobinTeam(agents=[user_proxy, assistant])

# Asynchronous chat function
async def start_conversation():
    print("Welcome to the Q&A Assistant! Ask your question (type 'quit' to exit).")
    await team.initiate_chat(
        messages.UserMessage(content="Start the conversation."),  # Initial message
        keep_running=True,  # Loop until termination
    )

# Run the async conversation
if __name__ == "__main__":
    asyncio.run(start_conversation())