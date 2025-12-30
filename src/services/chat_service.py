from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from src.core.exception import ChatServiceError, ServiceMaintenanceError
from src.rag import agent_rag


class ChatService:
    """
    Service layer for chat orchestration and RAG agent interactions.
    Handles both synchronous and streaming chat processing.
    """

    def __init__(self, agent: Any = None):
        """
        Initialize ChatService with a RAG agent.

        Args:
            agent: The RAG agent instance. Defaults to the global 'agent_rag'.
        """
        self.agent = agent or agent_rag

    async def process_chat(
        self,
        messages: str,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Process a standard chat request synchronously.

        Args:
            messages: The input text messages to process.
            conversation_id: Optional ID to track the conversation.
            metadata: Optional dictionary for tracking/analytical data.

        Returns:
            A dictionary containing the response content, conversation ID, and metadata.

        Raises:
            ServiceMaintenanceError: If the underlying RAG service is in maintenance mode.
            ChatServiceError: If an unexpected error occurs during processing.
        """
        try:
            logger.info(f"Processing chat request for conversation: {conversation_id}")

            # Use the RAG agent to compute the response
            result = await self.agent.ainvoke({"messages": messages})

            # Extract the final response message
            response_content = result["messages"][-1].content
            logger.info(f"Successfully processed chat for: {conversation_id}")

            return {
                "response": response_content,
                "conversation_id": conversation_id,
                "metadata": metadata or {},
            }

        except ServiceMaintenanceError:
            # Re-raise maintenance errors directly for upstream handling
            raise
        except Exception as e:
            logger.error(f"Failed to process chat ({conversation_id}): {str(e)}")
            raise ChatServiceError(f"Chat processing failed: {str(e)}") from e

    async def process_stream_chat(
        self, messages: str, conversation_id: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Process a chat request and stream the response character-by-character or token-by-token.

        Args:
            messages: The input text messages to process.
            conversation_id: Optional ID to track the conversation.

        Yields:
            Dictionaries containing message chunks or status updates (type: 'message', 'done', 'error').
        """
        try:
            logger.info(f"Initiating stream chat for conversation: {conversation_id}")

            # Stream message chunks from the RAG agent
            async for msg, _ in self.agent.astream({"messages": messages}, stream_mode="messages"):
                if msg.content:
                    yield {
                        "type": "message",
                        "content": msg.content,
                        "conversation_id": conversation_id,
                    }

            # Finalize the stream
            yield {"type": "done", "content": "", "conversation_id": conversation_id}
            logger.info(f"Stream chat finalized for: {conversation_id}")

        except ServiceMaintenanceError as e:
            logger.warning(f"RAG service in maintenance during stream: {e.service_name}")
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
            logger.error(f"Stream failure for conversation {conversation_id}: {str(e)}")
            yield {
                "type": "error",
                "data": {"error": f"Internal stream error: {str(e)}"},
                "conversation_id": conversation_id,
            }
