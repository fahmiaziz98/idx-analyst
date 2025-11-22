import asyncio
from typing import Any

from httpx import AsyncClient, HTTPError, TimeoutException
from loguru import logger

from src.core.circuit_breaker import CircuitBreakerConfig, get_circuit_breaker


class EmbeddingAPIClient:
    """
    Enhanced client for interacting with embedding API.

    Features:
    - Circuit breaker protection
    - Automatic retries with exponential backoff
    - Connection pooling
    - Request/response validation
    """

    def __init__(
        self, base_url: str, timeout: int = 300, max_retries: int = 3, enable_circuit_breaker: bool = True
    ) -> None:
        """
        Initialize embedding API client.

        Args:
            base_url: Base URL of embedding API
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            enable_circuit_breaker: Enable circuit breaker protection
        """
        self.base_url = base_url
        self.max_retries = max_retries
        self.client = AsyncClient(base_url=base_url, timeout=timeout)

        # Circuit breakers for different endpoints
        self.enable_circuit_breaker = enable_circuit_breaker
        if enable_circuit_breaker:
            cb_config = CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout=60,
                expected_exception=Exception,
            )
            self.embed_breaker = get_circuit_breaker("embedding_api", cb_config)
        else:
            self.embed_breaker = None

        logger.info(f"Embedding API client initialized: {base_url}")

    async def _make_request_with_retry(
        self, endpoint: str, payload: dict, retry_count: int = 0
    ) -> dict:
        """
        Make HTTP request with retry logic and exponential backoff.

        Args:
            endpoint: API endpoint
            payload: Request payload
            retry_count: Current retry attempt

        Returns:
            Response JSON

        Raises:
            Exception: After all retries fail
        """
        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()

        except (HTTPError, TimeoutException) as e:
            if retry_count < self.max_retries:
                # Exponential backoff: 2^retry_count seconds
                wait_time = 2**retry_count
                logger.warning(
                    f"Request to {endpoint} failed (attempt {retry_count + 1}/{self.max_retries}). "
                    f"Retrying in {wait_time}s... Error: {str(e)}"
                )
                await asyncio.sleep(wait_time)
                return await self._make_request_with_retry(endpoint, payload, retry_count + 1)
            else:
                logger.error(f"Request to {endpoint} failed after {self.max_retries} retries: {str(e)}")
                raise Exception(f"Failed after {self.max_retries} retries: {str(e)}") from e

        except Exception as e:
            logger.error(f"Unexpected error calling {endpoint}: {str(e)}")
            raise

    async def _make_request_protected(
        self, endpoint: str, payload: dict, circuit_breaker=None
    ) -> dict:
        """
        Make request with circuit breaker protection.

        Args:
            endpoint: API endpoint
            payload: Request payload
            circuit_breaker: Circuit breaker instance

        Returns:
            Response JSON
        """
        if circuit_breaker and self.enable_circuit_breaker:
            # Use circuit breaker
            return await circuit_breaker.call(self._make_request_with_retry, endpoint, payload)
        else:
            # Direct call without circuit breaker
            return await self._make_request_with_retry(endpoint, payload)

    async def get_dense_embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        """
        Get dense embeddings from API with circuit breaker protection.

        Args:
            model: Embedding model name
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            Exception: If API call fails
        """
        if not texts:
            logger.warning("Empty text list provided for embedding")
            return []

        logger.debug(f"Getting dense embeddings for {len(texts)} texts using model: {model}")

        try:
            data = await self._make_request_protected(
                "/embed", {"input": texts, "model": model}, self.embed_breaker
            )

            # Validate response
            if not isinstance(data, list):
                raise ValueError(f"Expected list response, got {type(data)}")

            logger.debug(f"Successfully retrieved {len(data)} dense embeddings")
            return data

        except Exception as e:
            logger.error(f"Failed to get dense embeddings: {str(e)}")
            raise

    async def get_sparse_embeddings(
        self, model: str, texts: list[str]
    ) -> list[dict[str, list]]:
        """
        Get sparse embeddings from API with circuit breaker protection.

        Args:
            model: Sparse embedding model name
            texts: List of texts to embed

        Returns:
            List of sparse embedding dictionaries

        Raises:
            Exception: If API call fails
        """
        if not texts:
            logger.warning("Empty text list provided for sparse embedding")
            return []

        logger.debug(f"Getting sparse embeddings for {len(texts)} texts using model: {model}")

        try:
            data = await self._make_request_protected(
                "/embed_sparse", {"input": texts, "model": model}, self.embed_breaker
            )

            # Validate response
            if not isinstance(data, list):
                raise ValueError(f"Expected list response, got {type(data)}")

            logger.debug(f"Successfully retrieved {len(data)} sparse embeddings")
            return data

        except Exception as e:
            logger.error(f"Failed to get sparse embeddings: {str(e)}")
            raise

    async def rerank_documents(
        self, query: str, documents: list[str], top_k: int = 5, model: str = "bge-v2-m3"
    ) -> list[dict]:
        """
        Rerank documents based on query with circuit breaker protection.

        Args:
            query: Search query
            documents: List of document texts
            top_k: Number of top documents to return
            model: Reranking model name

        Returns:
            List of reranked documents with scores

        Raises:
            Exception: If API call fails
        """
        if not documents:
            logger.warning("Empty document list provided for reranking")
            return []

        logger.debug(
            f"Reranking {len(documents)} documents with model: {model}, top_k: {top_k}"
        )

        try:
            data = await self._make_request_protected(
                "/rerank",
                {"query": query, "documents": documents, "top_k": top_k, "model": model},
                self.embed_breaker,
            )

            # Validate response
            if not isinstance(data, list):
                raise ValueError(f"Expected list response, got {type(data)}")

            logger.debug(f"Successfully reranked to top {len(data)} documents")
            return data

        except Exception as e:
            logger.error(f"Failed to rerank documents: {str(e)}")
            raise

    async def health_check(self) -> bool:
        """
        Check if embedding API is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get("/health", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Embedding API health check failed: {e}")
            return False

    async def close(self):
        """Close HTTP client connection."""
        await self.client.aclose()
        logger.info("Embedding API client closed")

    def get_circuit_breaker_stats(self) -> dict[str, Any]:
        """
        Get circuit breaker statistics.

        Returns:
            Dictionary with stats for all breakers
        """
        if not self.enable_circuit_breaker:
            return {"circuit_breaker": "disabled"}

        stats = {}
        if self.embed_breaker:
            stats["embedding"] = self.embed_breaker.get_stats()

        return stats


# Global client instance
_embedding_client: EmbeddingAPIClient | None = None


def get_embedding_client() -> EmbeddingAPIClient:
    """
    Get global embedding client instance.

    Returns:
        EmbeddingAPIClient singleton
    """
    global _embedding_client

    if _embedding_client is None:
        from src.core.config import settings

        _embedding_client = EmbeddingAPIClient(
            base_url=settings.EMBEDDING_API_URL,
            timeout=300,
            max_retries=3,
            enable_circuit_breaker=True,
        )

    return _embedding_client


async def close_embedding_client():
    """Close global embedding client."""
    global _embedding_client
    if _embedding_client:
        await _embedding_client.close()
        _embedding_client = None