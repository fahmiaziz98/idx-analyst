from datetime import UTC, datetime
from typing import Any

import httpx
from circuitbreaker import CircuitBreakerError, circuit
from loguru import logger

from src.core import settings
from src.core.exception import ServiceMaintenanceError


class EmbeddingAPIClient:
    """
    Client to interact with the external Embedding API service.
    Implements circuit breakers to handle service unavailability.
    """

    def __init__(
        self,
        base_url: str = settings.EMBEDDING_API_URL,
        timeout: int = 300,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self):
        await self.client.aclose()

    def _handle_circuit_error(self, e: CircuitBreakerError, service_name: str):
        """
        Helper to translate CircuitBreakerError into ServiceMaintenanceError
        Args:
            e (CircuitBreakerError): The caught circuit breaker error
            service_name (str): Name of the service for error reporting
        Returns:
            None
        """
        # CircuitBreaker lib calculates remaining time
        # Note: 'open_remaining' returns float seconds
        remaining = int(e._circuit_breaker.open_remaining)

        # Calculate absolute reset time
        # We use current UTC time + remaining seconds
        reset_time = datetime.now(UTC).replace(tzinfo=None)

        logger.warning(f"Circuit '{service_name}' OPEN. Remaining: {remaining}s")

        raise ServiceMaintenanceError(
            service_name=service_name, reset_time=reset_time, remaining_seconds=remaining
        ) from e

    # === Dense Embeddings ===
    @circuit(
        failure_threshold=2,
        recovery_timeout=60,
        expected_exception=httpx.HTTPError,
        name="embedding-dense",
    )
    async def _embed_dense_request(self, payload: dict):
        """
        Internal method to call dense embedding endpoint.
        Args:
            payload (dict): The request payload.
        Returns:
            dict: The response from the embedding service.
        """
        url = f"{self.base_url}/embeddings"
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def get_dense_embeddings(
        self, texts: str | list[str], model: str = "qwen3-0.6b"
    ) -> Any:
        """
        Public wrapper to handle circuit breaker errors gracefully.
        Args:
            texts (Union[str, List[str]]): The input text(s) to embed.
            model (str): The embedding model to use.
        Returns:
            dict: The embedding response.
        """
        try:
            payload = {"input": texts, "model": model}
            return await self._embed_dense_request(payload)

        except CircuitBreakerError as e:
            self._handle_circuit_error(e, "Embedding Service (Dense)")
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error in dense embedding: {e}")
            raise e

    # === Sparse Embeddings ===
    @circuit(
        failure_threshold=2,
        recovery_timeout=60,
        expected_exception=httpx.HTTPError,
        name="embedding-sparse",
    )
    async def _embed_sparse_request(self, payload: dict):
        """
        Internal method to call sparse embedding endpoint.
        Args:
            payload (dict): The request payload.
        Returns:
            dict: The response from the embedding service.
        """
        url = f"{self.base_url}/embed_sparse"
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def get_sparse_embeddings(
        self, texts: str | list[str], model: str = "splade-pp-v2"
    ) -> Any:
        """
        Public wrapper to handle circuit breaker errors gracefully.
        Args:
            texts (Union[str, List[str]]): The input text(s) to embed.
            model (str): The embedding model to use.
        Returns:
            dict: The embedding response.
        """
        try:
            payload = {"input": texts, "model": model}
            return await self._embed_sparse_request(payload)

        except CircuitBreakerError as e:
            self._handle_circuit_error(e, "Embedding Service (Sparse)")
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error in sparse embedding: {e}")
            raise e

    # === Reranking ===
    @circuit(
        failure_threshold=2,
        recovery_timeout=60,
        expected_exception=httpx.HTTPError,
        name="embedding-rerank",
    )
    async def _rerank_request(self, payload: dict):
        """
        Internal method to call reranking endpoint.
        Args:
            payload (dict): The request payload.
        Returns:
            dict: The response from the reranking service.
        """
        url = f"{self.base_url}/rerank"
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def rerank_documents(
        self, documents: list[str], query: str, model: str = "bge-v2-m3", top_k: int = 5
    ) -> Any:
        """
        Public wrapper to handle circuit breaker errors gracefully.
        Args:
            documents (List[str]): The list of documents to rerank.
            query (str): The query string.
            model (str): The reranking model to use.
            top_k (int): The number of top documents to return.
        Returns:
            dict: The reranking response.
        """
        try:
            payload = {
                "documents": documents,
                "model": model,
                "query": query,
                "top_k": top_k,
            }
            return await self._rerank_request(payload)

        except CircuitBreakerError as e:
            self._handle_circuit_error(e, "Reranking Service")
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error in reranking: {e}")
            raise e

    @staticmethod
    def get_circuit_status() -> dict[str, Any]:
        """Get monitoring status"""
        from circuitbreaker import CircuitBreakerMonitor

        return {
            c.name: {
                "state": "OPEN" if c.opened else "CLOSED",
                "failures": c.failure_count,
                "open_remaining": c.open_remaining if c.opened else 0,
            }
            for c in CircuitBreakerMonitor.get_circuits()
        }


_embedding_client_instance: EmbeddingAPIClient | None = None


def get_embedding_client() -> EmbeddingAPIClient:
    """
    Singleton accessor for EmbeddingAPIClient.
    Returns:
        EmbeddingAPIClient: The singleton instance.
    """
    global _embedding_client_instance
    if _embedding_client_instance is None:
        _embedding_client_instance = EmbeddingAPIClient()
    return _embedding_client_instance
