import asyncio
import os
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

async def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing OPENAI_API_KEY. Set it in your environment or a .env file."
        )

    model_client = OpenAIChatCompletionClient(model="gpt-4.1", api_key=api_key)
    agent = AssistantAgent("assistant", model_client=model_client)

    print(await agent.run(task="Say 'Hello World!'"))
    await model_client.close()

asyncio.run(main())




