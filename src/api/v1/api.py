from fastapi import APIRouter

from src.api.v1.endpoints import chat, websocket

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
