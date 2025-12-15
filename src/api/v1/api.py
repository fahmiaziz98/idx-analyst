from fastapi import APIRouter

from src.api.v1.endpoints import auth, chat, websocket

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
