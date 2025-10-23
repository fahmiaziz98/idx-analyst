import json
from datetime import datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from src.core import settings
from src.models.schemas import WebSocketMessage

router = APIRouter()


class ConnectionManager:
    """
    Manages WebSocket connections for real-time communication.
    """

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected: {session_id}")

    async def send_message(self, message: dict, session_id: str):
        """
        Send a message to a specific WebSocket connection.

        Args:
            message (dict): The message to send
            session_id (str): The session ID to send the message to
        """
        if session_id in self.active_connections:
            # Convert datetime objects to ISO format strings
            json_safe_message = self._prepare_message(message)
            json_message = json.dumps(json_safe_message)
            await self.active_connections[session_id].send_text(json_message)

    async def broadcast(self, message: dict):
        """
        Broadcast a message to all connected clients.
        """
        json_safe_message = self._prepare_message(message)
        json_message = json.dumps(json_safe_message)
        for connection in self.active_connections.values():
            await connection.send_text(json_message)

    def _prepare_message(self, message: dict) -> dict:
        """
        Prepare message for JSON serialization by converting datetime objects.

        Args:
            message (dict): Original message dictionary

        Returns:
            dict: JSON-safe message dictionary
        """

        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        return {key: convert_datetime(value) for key, value in message.items()}

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)


manager = ConnectionManager()


async def validate_ws_api_key(api_key: str | None) -> bool:
    """
    Validate API key for WebSocket connection
    """
    if not api_key:
        return False
    return api_key in settings.api_keys_list


@router.websocket("/chat")
async def websocket_endpoint(
    websocket: WebSocket,
    api_key: str | None = Query(None, alias="api_key"),
):
    if not await validate_ws_api_key(api_key):
        await websocket.close(code=1008)
        logger.warning("WebSocket connection rejected due to invalid API key")
        return

    # Generate client ID
    client_id = f"{websocket.client.host}:{websocket.client.port}"

    try:
        await manager.connect(websocket, client_id)

        # Send welcome message
        welcome_msg = WebSocketMessage(
            type="info",
            content="Connected to RAG Chatbot. Send your message!",
            metadata={"client_id": client_id},
        )
        await manager.send_message(welcome_msg.model_dump(), client_id)

        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                user_message = message_data.get("message", "")
                conversation_id = message_data.get("conversation_id")

                if not user_message:
                    error_msg = WebSocketMessage(
                        type="error",
                        content="Message cannot be empty",
                        conversation_id=conversation_id,
                    )
                    await manager.send_message(error_msg.model_dump(), client_id)
                    continue

                logger.info(f"WebSocket message received from {client_id}: {user_message[:50]}...")

                from src.rag import agent_rag

                ack_msg = WebSocketMessage(
                    type="info",
                    content="Processing your message...",
                    conversation_id=conversation_id,
                )

                await manager.send_message(ack_msg.model_dump(), client_id)

                # Stream response from graph
                full_response = ""
                async for msg, _ in agent_rag.astream(
                    {"messages": user_message}, stream_mode="messages"
                ):
                    if msg.content:
                        full_response += msg.content

                        chunk_msg = WebSocketMessage(
                            type="message",
                            content=msg.content,
                            conversation_id=conversation_id,
                            metadata={"streaming": True},
                        )
                        await manager.send_message(chunk_msg.model_dump(), client_id)

                done_msg = WebSocketMessage(
                    type="info",
                    content="[DONE]",
                    conversation_id=conversation_id,
                    metadata={"streaming": False, "total_length": len(full_response)},
                )
                await manager.send_message(done_msg.model_dump(), client_id)

                logger.info(f"WebSocket response sent to {client_id}: {len(full_response)} chars")

            except json.JSONDecodeError:
                error_msg = WebSocketMessage(type="error", content="Invalid JSON format")
                await manager.send_message(error_msg.model_dump(), client_id)
                logger.error(f"Invalid JSON from {client_id}")

            except Exception as e:
                error_msg = WebSocketMessage(
                    type="error", content=f"Error processing message: {str(e)}"
                )
                await manager.send_message(error_msg.model_dump(), client_id)
                logger.error(f"WebSocket processing error for {client_id}: {str(e)}")

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected normally")

    except Exception as e:
        manager.disconnect(client_id)
        logger.error(f"WebSocket error for {client_id}: {str(e)}")


@router.get("/connections")
async def get_connections():
    """
    Get number of active WebSocket connections (for monitoring)
    """
    return {"active_connections": manager.get_connection_count(), "timestamp": datetime.now()}
