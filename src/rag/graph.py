from typing import Any, Literal, cast

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from loguru import logger

from src.core import settings as config

from .prompts import (
    GENERAL_SYSTEM_PROMPT,
    MORE_INFO_SYSTEM_PROMPT,
    RESPONSE_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
)
from .researcher_graph import graph as research_graph
from .state import AgentState, InputState, Router
from .utils import format_docs

_ = load_dotenv(find_dotenv())


async def analyze_and_route_query(state: AgentState) -> dict[str, Router]:
    """
    Analyze the user's query and determine the appropriate routing.
    This function uses a language model to classify the user's query and decide how to route it
    within the conversation flow.

    Args:
        state (AgentState): The current state of the agent, including conversation history.

    Returns:
        dict[str, Router]: A dictionary containing the 'router' key with the classification result (classification type and logic).
    """
    logger.info(f"node analyze_route_query, messages => {state.messages[-1].content}")
    model = init_chat_model(config.MODEL_GEMINI_FLASH).with_structured_output(Router)
    messages = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}] + state.messages
    response = cast(Router, await model.ainvoke(messages))
    return {"router": response}


def route_query(
    state: AgentState,
) -> Literal["conduct_research", "ask_for_more_info", "respond_to_general_query"]:
    logger.info(f"node route_query, router => {state.router['router']}")
    _type = state.router["router"]
    if _type == "financial-statement":
        return "conduct_research"
    elif _type == "more-info":
        return "ask_for_more_info"
    elif _type == "general":
        return "respond_to_general_query"
    else:
        raise ValueError(f"Unknown router type {_type}")


async def ask_for_more_info(state: AgentState) -> dict[str, list[BaseMessage]]:
    """Generate a response asking the user for more information.

    This node is called when the router determines that more information is needed from the user.

    Args:
        state (AgentState): The current state of the agent, including conversation history and router logic.
        config (RunnableConfig): Configuration with the model used to respond.

    Returns:
        dict[str, list[str]]: A dictionary with a 'messages' key containing the generated response.
    """
    logger.info(f"node ask_for_more_info, messages => {state.messages[-1].content}")

    model = init_chat_model(config.MODEL_GEMINI_FLASH, max_tokens=2048, temperature=0.7)
    system_prompt = MORE_INFO_SYSTEM_PROMPT.format(logic=state.router["logic"])
    messages = [{"role": "system", "content": system_prompt}] + state.messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}


async def respond_to_general_query(state: AgentState) -> dict[str, list[BaseMessage]]:
    """
    Generate a response to a general query not related to LangChain.
    This node is called when the router classifies the query as a general question.

    Args:
        state (AgentState): The current state of the agent, including conversation history and router logic.

    Returns:
        dict[str, list[str]]: A dictionary with a 'messages' key containing the generated response.
    """
    logger.info(f"node respond_to_general_query, messages => {state.messages[-1].content}")
    system_prompt = GENERAL_SYSTEM_PROMPT.format(logic=state.router["logic"])
    model = init_chat_model(config.MODEL_GEMINI_FLASH, max_tokens=2048, temperature=0.7)
    messages = [{"role": "system", "content": system_prompt}] + state.messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}


async def conduct_research(state: AgentState) -> dict[str, Any]:
    """
    Conduct research based on the user's query and return relevant documents.
    This node is called when the router classifies the query as requiring research.

    Args:
        state (AgentState): The current state of the agent, including conversation history and router logic.

    Returns:
        dict[str, Any]: A dictionary with a 'documents' key containing the research results.
    """

    logger.info(f"node conduct_research, messages => {state.messages[-1].content}")
    result = await research_graph.ainvoke({"question": state.messages})
    return {"documents": result["documents"]}


async def respond(state: AgentState) -> dict[str, list[BaseMessage]]:
    """Generate a final response to the user's query based on the conducted research.

    This function formulates a comprehensive answer using the conversation history and the documents retrieved by the researcher.

    Args:
        state (AgentState): The current state of the agent, including retrieved documents and conversation history.
        config (RunnableConfig): Configuration with the model used to respond.

    Returns:
        dict[str, list[str]]: A dictionary with a 'messages' key containing the generated response.
    """
    logger.info(f"node respond, messages => {state.messages[-1].content}")
    context = format_docs(state.documents)
    prompt = RESPONSE_SYSTEM_PROMPT.format(context=context)
    model = init_chat_model(config.MODEL_GEMINI_FLASH, max_tokens=4096, temperature=0.7)
    messages = [{"role": "system", "content": prompt}] + state.messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}


# Define the graph
builder = StateGraph(AgentState, input_schema=InputState)
builder.add_node(analyze_and_route_query)
builder.add_node(ask_for_more_info)
builder.add_node(respond_to_general_query)
builder.add_node(conduct_research)
builder.add_node(respond)

builder.add_edge(START, "analyze_and_route_query")
builder.add_conditional_edges("analyze_and_route_query", route_query)
builder.add_edge("conduct_research", "respond")
builder.add_edge("ask_for_more_info", END)
builder.add_edge("respond_to_general_query", END)
builder.add_edge("respond", END)

# Compile into a graph object that you can invoke and deploy.
graph = builder.compile()
graph.name = "RetrievalGraph"
