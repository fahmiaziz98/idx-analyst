from datetime import datetime


class ServiceMaintenanceError(Exception):
    """
    Custom exception raised when the circuit breaker is open.
    Carries metadata for the frontend/user.
    """
    def __init__(self, service_name: str, reset_time: datetime, remaining_seconds: int):
        self.service_name = service_name
        self.reset_time = reset_time
        self.remaining_seconds = remaining_seconds
        self.message = (
            f"Service '{service_name}' is currently in cooldown/maintenance. "
            f"Please try again in {remaining_seconds} seconds."
        )
        super().__init__(self.message)

class EmbeddingServiceError(Exception):
    """
    Custom exception for embedding service errors.
    """
    def __init__(self, message: str, original_error: Exception = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)