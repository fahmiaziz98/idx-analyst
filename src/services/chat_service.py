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
    """

    def __init__(self, agent=None):
        """
        Initialize ChatService.
        
        Args:
            agent: The RAG agent to use. Defaults to the global agent_rag.
        """
        self.agent = agent or agent_rag

    async def process_chat(
        self,
        messages: str,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Process a non-streaming chat request.

        Args:
            messages: str of messages to process.
            conversation_id: Optional conversation ID.
            metadata: Optional metadata.

        Returns:
            Dictionary containing response, conversation ID, and metadata.
        """
        try:
            # Invoke RAG agent with messages
            result = await self.agent.ainvoke({"messages": messages})
            response_content = result["messages"][-1].content

            logger.info(f"Chat processed successfully. Conversation ID: {conversation_id}")

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

    async def process_stream_chat(
        self, messages: str, conversation_id: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Process a streaming chat request.

        Args:
            messages: str of messages to process.
            conversation_id: Optional conversation ID.

        Returns:
            Async generator yielding chat messages.
        """
        try:
            logger.info(f"Starting stream chat. Conversation ID: {conversation_id}")

            async for msg, _ in self.agent.astream({"messages": messages}, stream_mode="messages"):
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
