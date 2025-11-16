import asyncio

from httpx import AsyncClient, HTTPError, TimeoutException
from loguru import logger


class EmbeddingAPIClient:
    """
    Client for interacting with the embedding API.

    Parameters
    ----------
    base_url : str
        Base URL of the embedding API.
    timeout : int, optional
        Timeout (in seconds) for each request. Default is 600.
    max_retries : int, optional
        Maximum number of retry attempts when a request fails. Default is 3.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 600,
        max_retries: int = 3
    ) -> None:
        self.base_url = base_url
        self.max_retries = max_retries
        self.client = AsyncClient(base_url=base_url, timeout=timeout)

    async def _make_request_with_retry(
        self,
        endpoint: str,
        payload: dict,
        retry_count: int = 0
    ):
        """
        Helper method for making requests with retry logic.

        Parameters
        ----------
        endpoint : str
            API endpoint relative to `base_url`.
        payload : dict
            JSON payload to be sent.
        retry_count : int, optional
            Current attempt count. Default is 0.

        Returns
        -------
        dict
            JSON response from the API.

        Raises
        ------
        Exception
            If all attempts fail.
        """
        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()

        except (HTTPError, TimeoutException) as e:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count
                logger.warning(
                    f"⚠️  Request failed, retrying in {wait_time}s... "
                    f"(attempt {retry_count + 1}/{self.max_retries})"
                )
                await asyncio.sleep(wait_time)
                return await self._make_request_with_retry(
                    endpoint, payload, retry_count + 1
                )
            else:
                raise Exception(
                    f"❌ Failed after {self.max_retries} retries: {str(e)}"
                )

    async def get_dense_embeddings(
        self,
        model: str,
        texts: list[str]
    ) -> list[list[float]]:
        """
        Get dense embeddings from the API.

        Parameters
        ----------
        model : str
            Name of the embedding model.
        texts : list[str]
            List of texts to be embedded.

        Returns
        -------
        list[list[float]]
            List of embedding vectors for each text.
        """
        data = await self._make_request_with_retry(
            "/embed",
            {"input": texts, "model": model}
        )
        return data

    async def get_sparse_embeddings(
        self,
        model: str,
        texts: list[str]
    ) -> list[dict[str, list]]:
        """
        Get sparse embeddings from the API.

        Parameters
        ----------
        model : str
            Name of the embedding model.
        texts : list[str]
            List of texts to be embedded.

        Returns
        -------
        list[dict[str, list]]
            List of sparse embeddings for each text.
        """
        data = await self._make_request_with_retry(
            "/embed_sparse",
            {"input": texts, "model": model}
        )
        return data

    async def rerank_documents(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
        model: str = "bge-v2-m3"
    ) -> list[dict]:
        """
        Rerank documents based on the query.

        Parameters
        ----------
        query : str
            The question or search sentence.
        documents : list[str]
            List of documents (texts) to be reranked.
        top_k : int, optional
            Number of top documents to return. Default is 5.
        model : str, optional
            Name of the reranking model. Default is "bge-v2-m3".

        Returns
        -------
        list[dict]
            List of documents sorted by relevance.
        """
        data = await self._make_request_with_retry(
            "/rerank",
            {
                "query": query,
                "documents": documents,
                "top_k": top_k,
                "model": model
            }
        )
        return data

    async def close(self):
        """
        Close the HTTP client.
        """
        await self.client.aclose()
