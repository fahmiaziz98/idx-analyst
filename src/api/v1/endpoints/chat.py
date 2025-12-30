import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from src.api.middleware import limiter
from src.api.dependencies import get_current_user
from src.core.exception import ServiceMaintenanceError
from src.database.models import User
from src.schemas.chat import ChatRequest, ChatResponse, StreamChunk
from src.services.chat_service import ChatService

router = APIRouter()


@router.post("/", response_model=ChatResponse)
@limiter.limit("100/minute")
async def chat(
    request: Request,
    response: Response,
    body: ChatRequest,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    """
    Non-streaming chat endpoint.

    Processes a single chat request and returns a complete response.

    Request Body:
        - messages: List of chat messages
        - conversation_id: Optional conversation identifier
        - metadata: Optional additional metadata

    Returns:
        ChatResponse object with:
            - response: Generated text response
            - conversation_id: Conversation identifier
            - metadata: Associated metadata

    Raises:
        HTTPException: 503 if service is in maintenance mode
        HTTPException: 500 for any other server errors
    """
    try:
        chat_service = ChatService()
        result = await chat_service.process_chat(
            messages=body.messages, conversation_id=body.conversation_id, metadata=body.metadata
        )

        return ChatResponse(**result)

    except ServiceMaintenanceError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "service_maintenance",
                "message": e.message,
                "service": e.service_name,
                "retry_after": e.remaining_seconds,
                "available_at": e.reset_time.isoformat(),
            },
        ) from e

    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e


@router.post("/stream")
@limiter.limit("100/minute")
async def chat_stream(
    request: Request,
    response: Response,
    body: ChatRequest,
    user: User = Depends(get_current_user),
) -> EventSourceResponse:
    """
    Streaming chat endpoint (Server-Sent Events).

    Streams chat responses in real-time using SSE protocol.

    Request Body:
        - messages: List of chat messages
        - conversation_id: Optional conversation identifier
        - metadata: Optional additional metadata

    Returns:
        EventSourceResponse for Server-Sent Events

    SSE Events:
        - "message": Contains a chunk of the response
        - "done": Signals end of stream
        - "error": Contains error information if any
    """

    async def event_generator():
        """
        Internal generator for SSE events.

        Converts service layer chunks to SSE-compliant events.
        """
        chat_service = ChatService()
        async for chunk in chat_service.process_stream_chat(
            messages=body.messages, conversation_id=body.conversation_id
        ):
            if chunk["type"] == "message":
                stream_chunk = StreamChunk(
                    content=chunk["content"],
                    done=False,
                    metadata={"conversation_id": body.conversation_id},
                )
                yield {"event": "message", "data": stream_chunk.model_dump_json()}

            elif chunk["type"] == "done":
                yield {
                    "event": "done",
                    "data": StreamChunk(content="", done=True).model_dump_json(),
                }

            elif chunk["type"] == "error":
                yield {"event": "error", "data": json.dumps(chunk["data"])}

    return EventSourceResponse(event_generator())
