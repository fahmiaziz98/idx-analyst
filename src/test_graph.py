import asyncio

from rag import graph


async def test_graph(messages: str):
    result = await graph.ainvoke({"messages": messages})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    # asyncio.run(
    #     test_graph(
    #         "What was the total equity of PT BANK RAKYAT INDONESIA (PERSERO) Tbk and its subsidiaries as of December 31, 2024?"
    #     )
    # )
    asyncio.run(test_graph("Compare revenue bank Jago and BCA in 2024?"))
    # asyncio.run(test_graph("How does PT BANK JAGO Tbk classify its financial liabilities at initial recognition, and what are the characteristics and accounting treatment of financial liabilities classified as 'held for trading'?"))
    # asyncio.run(test_graph(" What were the details of the share buyback approved by PT Bank Central Asia Tbk's RUPSLB on May 26, 2005?"))
