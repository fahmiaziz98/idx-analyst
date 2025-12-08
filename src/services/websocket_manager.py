import json

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    """
    Manages WebSocket connections for a single user session.

    Attributes
    ----------
    active_connections : dict[str, WebSocket]
        Mapping of session identifiers to their active WebSocket objects.
    """

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """
        Accept a new WebSocket connection and register it.

        Args:
            websocket : WebSocket
                The WebSocket instance to accept.
            session_id : str
                Unique identifier for the user session.
        """
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WS Connected: {session_id}")

    def disconnect(self, session_id: str):
        """
        Remove a WebSocket connection from the registry.

        Args:
            session_id (str): Identifier of the session to disconnect.
        """
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WS Disconnected: {session_id}")

    async def send_json(self, message: dict, session_id: str):
        """
        Send a JSON‑serialisable message to a specific session.

        Args
            message (dict): The payload to send. Values that are not JSON‑serialisable
                (e.g., datetime) are converted to strings.
            session_id (str): Target session identifier.
        """
        if session_id in self.active_connections:
            json_str = json.dumps(message, default=str)
            await self.active_connections[session_id].send_text(json_str)

    def get_count(self) -> int:
        """
        Return the current number of active WebSocket connections.

        Returns:
            int: Count of active connections.
        """
        return len(self.active_connections)


_connection_instance: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """
    Singleton accessor for the global ConnectionManager instance.

    Returns:
        ConnectionManager: The shared connection manager used throughout the application.
    """
    global _connection_instance
    if _connection_instance is None:
        _connection_instance = ConnectionManager()
    return _connection_instance
