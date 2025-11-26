from typing import Any, TypedDict, cast

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from loguru import logger
from tavily import AsyncTavilyClient

from src.core import settings
from src.rag import prompts
from src.rag.utils import _generate_uuid
# from src.rag.vector_db import get_retriever_instance
from src.rag.vector_db.vectorstore import get_retriever_instance

from .state import QueryState, ResearcherState


async def generate_queries(state: ResearcherState) -> dict[str, list[str]]:
    """
    Generate search queries based on the question.
    This function uses a language model to generate diverse search queries to help answer the question.

    Args:
        state (ResearcherState): The current state of the researcher, including the user's question.

    Returns:
        dict[str, list[str]]: A dictionary with a 'queries' key containing the list of generated search queries.
    """

    class Response(TypedDict):
        queries: list[str]

    messages = [
        {"role": "system", "content": prompts.GENERATE_QUERIES_SYSTEM_PROMPT},
        {"role": "human", "content": f"Original queries: {state.question}"},
    ]

    llm = init_chat_model(model=settings.MODEL_GPT_OSS_20B).with_structured_output(Response)
    response = cast(Response, await llm.ainvoke(messages))
    logger.info(f"generate queries: {response['queries']}")
    return {"queries": response["queries"]}


async def retrieve_documents(state: QueryState) -> list[dict[str, Any]]:
    """
    Retrieve documents based on a given query.
    This function uses a retriever to fetch relevant documents for a given query.

    Args:
        state (QueryState): The current state containing the query string.

    Returns:
        dict[str, list[Document]]: A dictionary with a 'documents' key containing the list of retrieved documents.
    """
    logger.info(f"queries: {state.query}")
    retriever = get_retriever_instance()
    response = await retriever.search(
        state.query, 
        collection_name=settings.COLLECTION,
        dense_instruction=settings.INSTRUCTION_QUERY,
        top_k=20,
        use_reranking=True,
        use_cohere=False,
        rerank_top_k=10
    )
    return {"documents": response}   

async def web_search(state: QueryState) -> list[dict[str, Any]]:
    """
    Perform a web search based on a given query using Tavily.
    This function uses the Tavily client to fetch relevant web search results for a given query.

    Args:
        state (QueryState): The current state containing the query string.
    Returns:
        dict[str, list[dict[str, Any]]]: A dictionary with a 'web_results' key containing the list of web search results.
    """
    logger.info(f"Performing web search for query: {state.query}")
    client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
    search_results = await client.search(state.query, num_results=1, include_raw_content=False)

    format_documents = [
        {
            "id": _generate_uuid(doc["content"]),
            "chunk_text": doc["content"],
            "rerank_score": doc["score"],
            "metadata": {"url": doc["url"], "title": doc["title"]},
        }
        for doc in search_results["results"]
    ]

    return {"documents": format_documents}


def retrieve_in_parallel(state: ResearcherState) -> list[Send]:
    """
    Create parallel retrieval tasks for each generated query.
    This function prepares parallel document retrieval tasks for each query in the researcher's state.

    Args:
        state (ResearcherState): The current state of the researcher, including the generated queries.

    Returns:
        Literal["retrieve_documents"]: A list of Send objects, each representing a document retrieval task.

    Behavior:
        - Creates a Send object for each query in the state.
        - Each Send object targets the "retrieve_documents" node with the corresponding query.
    """
    sends = []
    for query in state.queries:
        sends.append(Send("retrieve_documents", QueryState(query=query)))
        sends.append(Send("web_search", QueryState(query=query)))
    return sends


builder = StateGraph(ResearcherState)
builder.add_node(generate_queries)
builder.add_node(web_search)
builder.add_node(retrieve_documents)
builder.add_edge(START, "generate_queries")
builder.add_conditional_edges(
    "generate_queries",
    retrieve_in_parallel,  # type: ignore
    path_map=["retrieve_documents", "web_search"],
)
builder.add_edge("web_search", END)
builder.add_edge("retrieve_documents", END)

# Compile into a graph object that you can invoke and deploy.
graph = builder.compile()
graph.name = "ResearcherGraph"
