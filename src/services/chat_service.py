from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from src.core.exception import ServiceMaintenanceError
from src.rag import agent_rag


class ChatService:
    """
    Service layer for chat-related business logic.

    This class encapsulates all business operations related to chat,
    providing a clean separation from API/HTTP concerns.

    Attributes:
        None (all methods are static/class methods)
    """

    @classmethod
    async def process_chat(
        cls,
        messages: list[dict[str, Any]],
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Process a non-streaming chat request.

        Args:
            messages: List of message dictionaries containing chat history
            conversation_id: Optional unique identifier for conversation tracking
            metadata: Optional additional metadata for the request

        Returns:
            Dictionary containing:
                - response: The generated response content
                - conversation_id: The provided or generated conversation ID
                - metadata: Any associated metadata

        Raises:
            ServiceMaintenanceError: If the service is currently in maintenance mode
            Exception: For any other errors during processing (to be handled upstream)

        Example:
            >>> result = await ChatService.process_chat(
            ...     messages=[{"role": "user", "content": "Hello"}],
            ...     conversation_id="conv_123",
            ...     metadata={"source": "web"}
            ... )
            >>> print(result["response"])
        """
        try:
            # Invoke RAG agent with messages
            result = await agent_rag.ainvoke({"messages": messages})
            response_content = result["messages"][-1].content

            logger.info(
                f"Chat processed successfully. Conversation ID: {conversation_id}, "
                f"Message count: {len(messages)}"
            )

            return {
                "response": response_content,
                "conversation_id": conversation_id,
                "metadata": metadata or {},
            }

        except ServiceMaintenanceError as e:
            logger.warning(
                f"Service maintenance during chat processing. "
                f"Service: {e.service_name}, "
                f"Retry after: {e.remaining_seconds}s"
            )
            raise

        except Exception as e:
            logger.error(
                f"Error processing chat request. "
                f"Conversation ID: {conversation_id}, "
                f"Error: {str(e)}"
            )
            raise

    @classmethod
    async def process_stream_chat(
        cls, messages: list[dict[str, Any]], conversation_id: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Process a streaming chat request.

        This method yields chunks of the response as they are generated,
        suitable for Server-Sent Events (SSE) or WebSocket streaming.

        Args:
            messages: List of message dictionaries containing chat history
            conversation_id: Optional unique identifier for conversation tracking

        Yields:
            Dictionary with structure:
                - type: One of "message", "done", "error"
                - content: Response content (for "message" type)
                - data: Error details (for "error" type)
                - conversation_id: Associated conversation ID

        Raises:
            ServiceMaintenanceError: If the service is currently in maintenance mode
            Exception: For any other errors during processing

        Example:
            >>> async for chunk in ChatService.process_stream_chat(
            ...     messages=[{"role": "user", "content": "Hello"}],
            ...     conversation_id="conv_123"
            ... ):
            ...     if chunk["type"] == "message":
            ...         print(chunk["content"])
        """
        try:
            logger.info(
                f"Starting stream chat. Conversation ID: {conversation_id}, "
                f"Message count: {len(messages)}"
            )

            async for msg, _ in agent_rag.astream({"messages": messages}, stream_mode="messages"):
                if msg.content:
                    yield {
                        "type": "message",
                        "content": msg.content,
                        "conversation_id": conversation_id,
                    }

            yield {"type": "done", "content": "", "conversation_id": conversation_id}

            logger.info(f"Stream chat completed. Conversation ID: {conversation_id}")

        except ServiceMaintenanceError as e:
            logger.warning(
                f"Service maintenance during stream chat. "
                f"Service: {e.service_name}, "
                f"Conversation ID: {conversation_id}"
            )
            yield {
                "type": "error",
                "data": {
                    "error": "service_maintenance",
                    "message": e.message,
                    "service": e.service_name,
                    "retry_after": e.remaining_seconds,
                    "available_at": e.reset_time.isoformat(),
                },
                "conversation_id": conversation_id,
            }

        except Exception as e:
            logger.error(
                f"Error in stream chat. Conversation ID: {conversation_id}, Error: {str(e)}"
            )
            yield {"type": "error", "data": {"error": str(e)}, "conversation_id": conversation_id}
