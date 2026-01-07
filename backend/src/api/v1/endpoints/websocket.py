import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from src.auth.jwt import verify_token
from src.database.models import MessageRole
from src.database.session import AsyncSessionLocal
from src.services.messages_service import MessageService
from src.services.chat_service import ChatService
from src.services.websocket_manager import get_connection_manager

router = APIRouter()
manager = get_connection_manager()


@router.websocket("/chat")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None, alias="token"),
):
    """
    WebSocket endpoint for real-time chat interaction
    with the RAG Chatbot.
    Client must provide a valid JWT token as a query parameter.

    Args:
        websocket: WebSocket connection object.
        token: JWT token for authentication.
    """
    if not token:
        token = websocket.cookies.get("access_token")

    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    token_data = verify_token(token)
    if not token_data:
        await websocket.close(code=1008, reason="Invalid token")
        return

    client_id = f"{websocket.client.host}:{websocket.client.port}"

    async with AsyncSessionLocal() as session:
        message_service = MessageService(session)
        chat_service = ChatService()

        try:
            await manager.connect(websocket, client_id)

            await manager.send_json({"type": "info", "content": "Connected to RAG Chatbot"}, client_id)

            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                user_message = message_data.get("message", "")
                conversation_id = message_data.get("conversation_id")

                if not user_message:
                    continue

                # 1. Save User Message (uses connection-level session)
                try:
                    await message_service.create_message(
                        conversation_id=conversation_id,
                        role=MessageRole.USER,
                        content=user_message
                    )
                except Exception as e:
                    logger.error(f"Failed to save user message: {e}")
                    # Continue anyway to allow chat to proceed
            
                full_response = ""
                
                async for chunk in chat_service.process_stream_chat(
                    messages=user_message, conversation_id=conversation_id
                ):
                    if chunk["type"] == "message":
                        full_response += chunk["content"]
                        await manager.send_json(
                            {
                                "type": "message",
                                "content": chunk["content"],
                                "conversation_id": conversation_id,
                                "metadata": {"streaming": True},
                            },
                            client_id,
                        )
                    elif chunk["type"] == "done":
                         await manager.send_json(
                            {
                                "type": "info",
                                "content": "[DONE]",
                                "conversation_id": conversation_id,
                                "metadata": {"streaming": False, "total_length": len(full_response)},
                            },
                            client_id,
                        )
                    elif chunk["type"] == "error":
                        error_data = chunk.get("data", {})
                        error_msg = error_data.get("message") or error_data.get("error") or "Unknown error"
                        await manager.send_json(
                            {"type": "error", "content": str(error_msg), "conversation_id": conversation_id}, 
                            client_id
                        )

                # 2. Save Assistant Message (uses connection-level session)
                if full_response:
                    try:
                        await message_service.create_message(
                            conversation_id=conversation_id,
                            role=MessageRole.ASSISTANT,
                            content=full_response
                        )
                    except Exception as e:
                        logger.error(f"Failed to save assistant message: {e}")

        except WebSocketDisconnect:
            manager.disconnect(client_id)
        except Exception as e:
            logger.error(f"WS Error: {e}")
            await manager.send_json({"type": "error", "content": str(e)}, client_id)
            manager.disconnect(client_id)
