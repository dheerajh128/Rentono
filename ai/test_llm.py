import asyncio
from ai.services.llm_service import get_llm

async def main():
    llm = get_llm()

    response = await llm.ainvoke(
        "Reply with exactly: Groq is working!"
    )

    print(response.content)

asyncio.run(main())