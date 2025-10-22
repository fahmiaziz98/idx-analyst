import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from src.api.dependencies import get_current_api_key
from src.models.schemas import ChatRequest, ChatResponse, StreamChunk

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Non-streaming chat endpoint",
    dependencies=[Depends(get_current_api_key)],
)
async def chat(request: ChatRequest):
    """
    Non-streaming chat endpoint

    - **message**: User message/query
    - **conversation_id**: Optional conversation ID for context
    - **metadata**: Additional metadata
    """
    try:
        logger.info(f"Chat request received: {request.messages[:50]}...")

        from src.rag import agent_rag

        result = await agent_rag.ainvoke({"messages": request.messages})
        response_content = result["messages"][-1].content

        return ChatResponse(
            response=response_content,
            conversation_id=request.conversation_id,
            metadata=request.metadata,
        )

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat request: {str(e)}",
        ) from e


@router.post(
    "/chat/stream",
    summary="Streaming chat endpoint (SSE)",
    dependencies=[Depends(get_current_api_key)],
)
async def chat_stream(request: ChatRequest):
    """
    Server-Sent Events (SSE) streaming chat endpoint

    - **message**: User message/query
    - **conversation_id**: Optional conversation ID for context
    - **metadata**: Additional metadata

    Returns streaming response in SSE format
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            logger.info(f"Stream chat request: {request.messages[:50]}...")

            from src.rag import agent_rag

            async for msg, _ in agent_rag.astream(
                {"messages": request.messages}, stream_mode="messages"
            ):
                if msg.content:
                    chunk = StreamChunk(
                        content=msg.content,
                        done=False,
                        metadata={"conversation_id": request.conversation_id},
                    )
                    yield {"event": "message", "data": chunk.model_dump_json()}

            # Send completion signal
            final_chunk = StreamChunk(
                content="", done=True, metadata={"conversation_id": request.conversation_id}
            )
            yield {"event": "done", "data": final_chunk.model_dump_json()}

            logger.info("Stream completed successfully")

        except Exception as e:
            logger.error(f"Stream error: {str(e)}")
            error_chunk = {"event": "error", "data": json.dumps({"error": str(e)})}
            yield error_chunk

    return EventSourceResponse(event_generator())
