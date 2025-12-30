import json

from fastapi import WebSocket
from loguru import logger

from src.core.exception import WebSocketManagerError


class ConnectionManager:
    """
    Manages active WebSocket connections across different user sessions.
    Handles connection lifecycle (connect, disconnect) and selective broadcasting.
    """

    def __init__(self):
        """
        Initialize the connection manager with an empty registry of active sessions.
        """
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """
        Accept an incoming WebSocket connection and register it for the given session.

        Args:
            websocket: The FastAPI WebSocket object to be accepted.
            session_id: A unique identifier for the user session.

        Raises:
            WebSocketManagerError: If the connection cannot be accepted.
        """
        try:
            await websocket.accept()
            self.active_connections[session_id] = websocket
            logger.info(f"WebSocket session established: {session_id}")
        except Exception as e:
            logger.error(f"Failed to accept WebSocket for session {session_id}: {str(e)}")
            raise WebSocketManagerError(
                f"Could not establish WebSocket connection: {str(e)}"
            ) from e

    def disconnect(self, session_id: str):
        """
        Deregister and remove a WebSocket connection from the active registry.

        Args:
            session_id: The identifier of the session to terminate.
        """
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket session terminated: {session_id}")

    async def send_json(self, message: dict, session_id: str):
        """
        Send a JSON‑serializable payload to a specific active session.

        Args:
            message: The data dictionary to send. Non-standard types are cast to strings.
            session_id: The target session identifier.

        Raises:
            WebSocketManagerError: If sending the message fails unexpectedly.
        """
        websocket = self.active_connections.get(session_id)
        if not websocket:
            logger.debug(f"Attempted to send message to inactive session: {session_id}")
            return

        try:
            # Handle non-serializable objects by converting to str in default
            json_payload = json.dumps(message, default=str)
            await websocket.send_text(json_payload)
        except Exception as e:
            logger.error(f"Error sending WebSocket message to {session_id}: {str(e)}")
            # We don't always want to raise here to avoid crashing the caller,
            # but we log it and ensure the session is cleaned up if the socket is dead.
            self.disconnect(session_id)
            raise WebSocketManagerError(f"Failed to transmit data to session {session_id}") from e

    def get_active_count(self) -> int:
        """
        Get the current number of active WebSocket connections.

        Returns:
            The total count of registered sessions.
        """
        return len(self.active_connections)


# Singleton instance shared application-wide
_manager_instance: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """
    Retrieve the global singleton instance of the ConnectionManager.

    Returns:
        The shared ConnectionManager instance.
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ConnectionManager()
    return _manager_instance
