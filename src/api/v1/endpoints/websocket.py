import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from src.auth.jwt import verify_token
from src.rag import agent_rag
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
    """
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    token_data = verify_token(token)
    if not token_data:
        await websocket.close(code=1008, reason="Invalid token")
        return

    client_id = f"{websocket.client.host}:{websocket.client.port}"

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

            full_response = ""
            async for msg, _ in agent_rag.astream(
                {"messages": user_message}, stream_mode="messages"
            ):
                if msg.content:
                    full_response += msg.content
                    await manager.send_json(
                        {
                            "type": "message",
                            "content": msg.content,
                            "conversation_id": conversation_id,
                            "metadata": {"streaming": True},
                        },
                        client_id,
                    )

            await manager.send_json(
                {
                    "type": "info",
                    "content": "[DONE]",
                    "conversation_id": conversation_id,
                    "metadata": {"streaming": False, "total_length": len(full_response)},
                },
                client_id,
            )

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WS Error: {e}")
        await manager.send_json({"type": "error", "content": str(e)}, client_id)
        manager.disconnect(client_id)
