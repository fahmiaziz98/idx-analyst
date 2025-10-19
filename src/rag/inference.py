import asyncio
from typing import Any

import httpx
from loguru import logger


class InferenceClient:
    """
    Client for interacting with Unified Embedding & Reranking API.

    Supports both embedding and reranking operations, with automatic
    model listing, connection testing, and retry mechanism.
    """

    def __init__(self, base_url: str, rerank_url: str):
        """
        Initialize the client with the API base URL.

        Args:
            base_url (str): Root endpoint of the embedding API (e.g. 'https://your-api.hf.space')
            rerank_url (str): Root endpoint of the reranking API.
        """
        self.base_url = base_url.rstrip("/")
        self.rerank_url = rerank_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=120)
        self.max_retries = 5
        self.retry_delay = 2

    async def _test_connection(self) -> bool:
        """Check if the API server is reachable and healthy."""
        try:
            response_base = await self.client.get(f"{self.base_url}/health")
            response_rerank = await self.client.get(f"{self.rerank_url}/health")
            if response_base.status_code == 200 and response_rerank.status_code == 200:
                logger.success("✅ API connection successful!")
                return True
            logger.warning(f"⚠️ API health check returned unexpected response: {response_base.text}")
            return False
        except httpx.RequestError as e:
            logger.error(f"❌ Failed to connect to API: {e}")
            return False

    async def list_available_models(self) -> dict[str, list[dict[str, Any]]]:
        """List all available reranking and embedding models."""
        try:
            embedding_resp = await self.client.get(f"{self.base_url}/models")
            rerank_resp = await self.client.get(f"{self.rerank_url}/models")

            embedding_models = embedding_resp.json() if embedding_resp.status_code == 200 else []
            rerank_models = rerank_resp.json() if rerank_resp.status_code == 200 else []

            logger.info(
                f"Found {len(embedding_models)} embedding models and {len(rerank_models)} reranking models"
            )

            return {"embedding": embedding_models, "rerank": rerank_models}

        except Exception as e:
            logger.error(f"Failed to fetch available models: {e}")
            return {"embedding": [], "rerank": []}

    async def _post_with_retry(self, url: str, payload: dict[str, Any]) -> httpx.Response | None:
        """
        Internal helper for POST requests with retry logic.

        Retries up to `self.max_retries` times with exponential backoff
        if the request fails or returns a non-200 status code.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.post(url, json=payload)
                if response.status_code == 200:
                    return response
                else:
                    logger.warning(
                        f"Attempt {attempt}/{self.max_retries} failed with status {response.status_code}: {response.text}"
                    )
            except httpx.RequestError as e:
                logger.warning(f"Attempt {attempt}/{self.max_retries} request error: {e}")

            if attempt < self.max_retries:
                delay = self.retry_delay * (2 ** (attempt - 1))
                logger.info(f"⏳ Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

        logger.error(f"All {self.max_retries} attempts failed for URL: {url}")
        return None

    async def query(
        self, text: str, model_id: str, prompt: str | None = None
    ) -> list[list[float]] | None:
        """
        Generate embeddings for a list of input texts with retry logic.

        Args:
            texts (List[str]): List of input sentences.
            model_id (str): Model identifier.
            prompt (Optional[str]): Optional prefix prompt for instruction-based models.
        """
        payload = {"text": text, "model_id": model_id}
        if prompt:
            payload["prompt"] = prompt

        response = await self._post_with_retry(f"{self.base_url}/query", payload)
        return response.json() if response else None

    async def embed(
        self, text: str, model_id: str, prompt: str | None = None
    ) -> list[list[float]] | None:
        """
        Generate embeddings for a list of input texts with retry logic.

        Args:
            texts (List[str]): List of input sentences.
            model_id (str): Model identifier.
            prompt (Optional[str]): Optional prefix prompt for instruction-based models.
        """
        payload = {"text": text, "model_id": model_id}
        if prompt:
            payload["prompt"] = prompt

        response = await self._post_with_retry(f"{self.base_url}/embed", payload)
        return response.json() if response else None

    async def embed_batch(
        self, batches: list[str], model_id: str, prompt: str | None = None
    ) -> list[list[float]] | None:
        """
        Generate embeddings for multiple batches of text with retry logic.
        """
        payload = {"texts": batches, "model_id": model_id}
        if prompt:
            payload["prompt"] = prompt

        response = await self._post_with_retry(f"{self.base_url}/embed/batch", payload)
        return response.json() if response else None

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model_id: str,
        top_k: int | None = None,
        prompt: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """
        Rerank a list of documents given a query using retry logic.
        """
        payload = {"query": query, "documents": documents, "model_id": model_id}
        if prompt:
            payload["instruction"] = prompt
        if top_k:
            payload["top_k"] = top_k

        response = await self._post_with_retry(f"{self.rerank_url}/rerank", payload)
        return response.json() if response else None

    async def close(self):
        """Gracefully close the HTTP client."""
        await self.client.aclose()
        logger.info("Closed API client session.")
