import httpx
from loguru import logger
from typing import List, Dict, Any, Optional


class InferenceClient:
    """
    Client for interacting with Unified Embedding & Reranking API.

    Supports both embedding and reranking operations, with automatic
    model listing and connection testing.
    """

    def __init__(self, base_url: str, rerank_url: str):
        """
        Initialize the client with the API base URL.

        Args:
            base_url (str): The root endpoint of the API (e.g. 'https://your-api.hf.space')
            rerank_url (str): The root endpoint for the reranking API.
        """
        self.base_url = base_url.rstrip("/")
        self.rerank_url = rerank_url.rstrip("/")
        self.client = httpx.AsyncClient()


    async def _test_connection(self) -> bool:
        """
        Check if the API server is reachable and healthy.

        Returns:
            bool: True if API is reachable and healthy, False otherwise.
        """
        try:
            response_base = await self.client.get(f"{self.base_url}/health")
            response_rerank = await self.client.get(f"{self.rerank_url}/health")
            if response_base.status_code == 200 and response_rerank.status_code == 200:
                logger.success("✅ API connection successful!")
                return True
            logger.warning("⚠️ API health check returned unexpected response")
            return False
        except httpx.RequestError as e:
            logger.error(f"❌ Failed to connect to API: {e}")
            return False

    async def list_available_models(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all available reranking and embedding models.

        Returns:
            dict: A dictionary containing two lists — `embedding` and `rerank` models.
        """
        try:
            embedding_resp = await self.client.get(f"{self.base_url}/models")
            rerank_resp = await self.client.get(f"{self.rerank_url}/models")

            embedding_models = embedding_resp.json() if embedding_resp.status_code == 200 else []
            rerank_models = rerank_resp.json() if rerank_resp.status_code == 200 else []

            logger.info(f"📦 Found {len(embedding_models)} embedding models and {len(rerank_models)} reranking models")

            return {
                "embedding": embedding_models,
                "rerank": rerank_models
            }

        except Exception as e:
            logger.error(f"Failed to fetch available models: {e}")
            return {"embedding": [], "rerank": []}

    async def embed(
        self,
        texts: str,
        model_id: str,
        prompt: Optional[str] = None
    ) -> Optional[List[List[float]]]:
        """
        Generate embeddings for a list of input texts.

        Args:
            texts (List[str]): List of input sentences.
            model_id (str): Model identifier from config.yaml.
            prompt (Optional[str]): Optional prefix prompt for instruction-based models.

        Returns:
            List[List[float]]: List of embedding vectors, or None if failed.
        """
        try:
            payload = {"text": texts, "model_id": model_id}
            if prompt:
                payload["prompt"] = prompt

            response = await self.client.post(f"{self.base_url}/embed", json=payload)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Embedding failed: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Embedding request failed: {e}")
            return None

    async def embed_batch(
        self,
        batches: List[str],
        model_id: str,
        prompt: Optional[str] = None
    ) -> Optional[List[List[float]]]:
        """
        Generate embeddings for multiple batches of text.

        Useful when processing large datasets that need to be split
        into smaller chunks for memory efficiency.

        Args:
            batches (List[List[str]]): List of text batches.
            model_id (str): Model identifier.
            prompt (Optional[str]): Optional prefix prompt.

        Returns:
            List[List[float]]: Combined list of embeddings from all batches.
        """
        try:
            payload = {"texts": batches, "model_id": model_id}
            if prompt:
                payload["prompt"] = prompt

            response = await self.client.post(f"{self.base_url}/embed/batch", json=payload)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Batch embedding failed: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Batch embedding request failed: {e}")
            return None

    async def rerank(
        self,
        query: str,
        documents: List[str],
        model_id: str,
        top_k: Optional[int] = None,
        prompt: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Rerank a list of documents given a query using a reranking model.

        Args:
            query (str): Input query text.
            documents (List[str]): List of candidate documents.
            model_id (str): Model identifier for reranking.
            prompt (Optional[str]): Optional instruction/prompt for reranker models.

        Returns:
            List[Dict[str, Any]]: Ranked documents with scores and indices.
        """
        try:
            payload = {"query": query, "documents": documents, "model_id": model_id}
            if prompt:
                payload["instruction"] = prompt  
            if top_k:
                payload["top_k"] = top_k

            response = await self.client.post(f"{self.rerank_url}/rerank", json=payload)
            if response.status_code == 200:
                return response.json().get("results", [])
            else:
                logger.error(f"Rerank failed: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Rerank request failed: {e}")
            return None

    async def close(self):
        """Gracefully close the HTTP client."""
        await self.client.aclose()
        logger.info("Closed API client session.")
