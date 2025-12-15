import asyncio
import time
from datetime import datetime
from typing import Any

import cohere
import numpy as np
from loguru import logger
from portalocker.exceptions import AlreadyLocked
from qdrant_client import AsyncQdrantClient, models
from tqdm.asyncio import tqdm as async_tqdm

from src.core import settings
from src.core.exception import ServiceMaintenanceError
from src.rag.embedding_client import get_embedding_client


class QdrantVectoreStore:
    """
    Enhanced wrapper class for Qdrant client with circuit breaker protection

    Features:
    - Complete document information preservation
    - Circuit breaker error handling for all embedding operations
    - User-friendly maintenance messages
    - Hybrid search (dense + sparse)
    - Reranking support (local + Cohere)
    """

    def __init__(
        self,
        path_client: str = "./local_db",
        is_local: bool = False,
    ):
        """
        Initialize QdrantClientWrapper with embedding and reranking clients.

        Args:
            config: setting config
            path_client: Path for local Qdrant storage
            is_local: Whether to use local Qdrant instance
        """
        self.config = settings
        self.api_client = get_embedding_client()
        self.co = cohere.Client(self.config.COHERE_API_KEY)

        self.DENSE_VECTOR_NAME = "dense"
        self.SPARSE_VECTOR_NAME = "sparse"

        if is_local:
            try:
                self.client = AsyncQdrantClient(path=path_client)
                logger.success(f"Successfully created local Qdrant client at `{path_client}`")
            except AlreadyLocked:
                logger.warning(
                    f"Local storage folder `{path_client}` is already locked. Cannot create new client."
                )
                self.client = None
        else:
            try:
                self.client = AsyncQdrantClient(
                    url=self.config.QDRANT_BASE_URL,
                    api_key=self.config.QDRANT_API_KEY,
                    timeout=60,
                    check_compatibility=False,
                )
                logger.success("Successfully created remote Qdrant client")
            except Exception as e:
                logger.error(f"Failed to create remote Qdrant client: {e}")
                self.client = None
                raise

    async def create_collection(self, collection_name: str, dimension: int):
        """
        Create collection with hybrid vector configuration.

        Args:
            collection_name: Name of the collection to create
            dimension: Dimension of dense vectors
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return
        try:
            collections_response = await self.client.get_collections()
            existing = collections_response.collections
            if not any(collection.name == collection_name for collection in existing):
                _ = await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        self.DENSE_VECTOR_NAME: models.VectorParams(
                            size=dimension,
                            distance=models.Distance.COSINE,
                            on_disk=True,
                            quantization_config=models.BinaryQuantization(
                                binary=models.BinaryQuantizationConfig(always_ram=True)
                            ),
                        )
                    },
                    sparse_vectors_config={
                        self.SPARSE_VECTOR_NAME: models.SparseVectorParams(
                            index=models.SparseIndexParams(on_disk=False),
                            modifier=models.Modifier.IDF,
                        )
                    },
                    hnsw_config=models.HnswConfigDiff(
                        m=8,
                        ef_construct=32,
                        full_scan_threshold=10000,
                        max_indexing_threads=0,
                        on_disk=True,
                        payload_m=16,
                    ),
                    optimizers_config=models.OptimizersConfigDiff(
                        deleted_threshold=0.2,
                        vacuum_min_vector_number=1000,
                        default_segment_number=2,
                        max_segment_size=None,
                        indexing_threshold=50000,
                        flush_interval_sec=10,
                        max_optimization_threads=0,
                    ),
                )
                logger.success(f"Successfully created collection `{collection_name}`")
            else:
                logger.info(f"Collection `{collection_name}` already exists.")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")

    async def upload_documents(
        self,
        collection_name: str,
        documents: list[dict[str, Any]],
        dense_model: str = "qwen3-0.6b",
        sparse_model: str = "splade-pp-v2",
        dense_instruction: str | None = None,
        batch_size: int = 32,
        text_field: str = "contextual_text",
        disable_indexing: bool = True,
    ) -> dict[str, int]:
        """
        Upload documents to collection with circuit breaker protection

        Args:
            collection_name: Target collection name
            documents: List of documents to upload
                Format: [{"id": ..., "chunk_text": ..., "contextual_text": ..., "metadata": {...}}, ...]
            dense_model: Dense embedding model ID
            sparse_model: Sparse embedding model ID
            dense_instruction: Optional instruction for dense embedding
            batch_size: Batch size for processing
            text_field: Primary text field to embed
            disable_indexing: Disable HNSW during upload (re-enable after)

        Returns:
            {"successful": count, "failed": count}

        Raises:
            ServiceMaintenanceError: When embedding service is in maintenance mode
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return {"successful": 0, "failed": 0}

        total_docs = len(documents)
        successful_count = 0
        failed_count = 0

        logger.info(f"Uploading {total_docs} documents to '{collection_name}'")
        logger.info(f"  Dense model: {dense_model}")
        logger.info(f"  Sparse model: {sparse_model}")
        logger.info(f"  Batch size: {batch_size}")

        if disable_indexing:
            logger.info("Disabling HNSW indexing for bulk upload...")
            try:
                await self.client.update_collection(
                    collection_name=collection_name, hnsw_config=models.HnswConfigDiff(m=0)
                )
            except Exception as e:
                logger.warning(f"Failed to disable indexing: {e}")

        try:
            for i in async_tqdm(range(0, total_docs, batch_size), desc="Uploading batches"):
                batch = documents[i : i + batch_size]
                points = []

                texts = []
                for doc in batch:
                    text = doc.get(text_field, "")
                    texts.append(text)

                texts_dense = texts
                if dense_instruction:
                    texts_dense = [f"{dense_instruction}: {text}" for text in texts]

                try:
                    dense_responses = await self.api_client.get_dense_embeddings(
                        texts=texts_dense, model=dense_model
                    )

                    sparse_responses = await self.api_client.get_sparse_embeddings(
                        texts=texts, model=sparse_model
                    )

                    for doc, dense_resp, sparse_resp in zip(
                        batch, dense_responses, sparse_responses, strict=False
                    ):
                        try:
                            dense_embedding = self._parse_dense_embedding(dense_resp)
                            sparse_dict = self._parse_sparse_embedding(sparse_resp)
                            sparse_vector = self._format_sparse_for_qdrant(sparse_dict)

                            point = models.PointStruct(
                                id=doc.get("id"),
                                vector={
                                    self.DENSE_VECTOR_NAME: dense_embedding,
                                    self.SPARSE_VECTOR_NAME: sparse_vector,
                                },
                                payload={
                                    "id": doc.get("id"),
                                    "contextual_text": doc.get("contextual_text", ""),
                                    "chunk_text": doc.get("chunk_text", ""),
                                    "metadata": doc.get("metadata", {}),
                                    "dense_model": dense_model,
                                    "sparse_model": sparse_model,
                                    "upload_timestamp": datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                },
                            )
                            points.append(point)

                        except Exception as e:
                            logger.error(f"Failed to process doc {doc.get('id')}: {e}")
                            failed_count += 1
                            continue

                    # Upload batch
                    if points:
                        await self.client.upsert(
                            collection_name=collection_name, points=points, wait=False
                        )
                        successful_count += len(points)

                except Exception as e:
                    logger.error(f"Failed to process batch: {e}")
                    failed_count += len(batch)
                    continue

            logger.success(f"Upload complete: {successful_count} succeeded, {failed_count} failed")

            # Re-enable indexing
            if disable_indexing:
                logger.info("Re-enabling HNSW indexing...")
                try:
                    await self.client.update_collection(
                        collection_name=collection_name,
                        hnsw_config=models.HnswConfigDiff(m=8, ef_construct=32),
                    )
                    logger.info("Indexing re-enabled. Building index...")
                except Exception as e:
                    logger.error(f"Failed to re-enable indexing: {e}")

            return {"successful": successful_count, "failed": failed_count}

        except ServiceMaintenanceError:
            raise

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return {"successful": successful_count, "failed": failed_count}

    async def search(
        self,
        query: str,
        collection_name: str,
        dense_model: str = "qwen3-0.6b",
        sparse_model: str = "splade-pp-v2",
        dense_instruction: str | None = None,
        top_k: int = 20,
        use_reranking: bool = False,
        rerank_model: str | None = "bge-v2-m3",
        rerank_top_k: int = 10,
        use_cohere: bool = False,
        cohere_model: str = "rerank-english-v3.0",
    ) -> list[dict[str, Any]]:
        """
        Hybrid search with circuit breaker protection

        Args:
            query: Search query
            collection_name: Collection name
            dense_model: Dense embedding model
            sparse_model: Sparse embedding model
            dense_instruction: Dense embedding instruction
            top_k: Initial retrieval count
            use_reranking: Apply reranking
            rerank_model: Reranking model ID
            rerank_top_k: Final top-k after reranking
            use_cohere: Use Cohere for reranking
            cohere_model: Cohere rerank model

        Returns:
            List of documents with scores

        Raises:
            ServiceMaintenanceError: When embedding service is in maintenance mode
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return []

        start_time = time.perf_counter()

        try:
            logger.info("Generating query embeddings...")

            start_embed = time.perf_counter()

            query_dense = query
            if dense_instruction:
                query_dense = f"{dense_instruction}: {query}"

            dense_task = self.api_client.get_dense_embeddings(
                texts=[query_dense], model=dense_model
            )
            sparse_task = self.api_client.get_sparse_embeddings(texts=[query], model=sparse_model)
            dense_resp, sparse_resp = await asyncio.gather(dense_task, sparse_task)

            end_time = time.perf_counter() - start_embed
            logger.info(f"Duration generate embedding & sparse: {end_time * 1000:.1f}ms")

            logger.info("Start execute hybrid search...")
            start_query = time.perf_counter()

            # Parse embeddings
            dense_embedding = self._parse_dense_embedding(dense_resp[0])
            sparse_dict = self._parse_sparse_embedding(sparse_resp[0])
            sparse_vector = self._format_sparse_for_qdrant(sparse_dict)

            # Prepare prefetch queries
            prefetch_queries = [
                models.Prefetch(
                    query=np.array(dense_embedding, dtype=np.float32),
                    using=self.DENSE_VECTOR_NAME,
                    limit=top_k,
                ),
                models.Prefetch(query=sparse_vector, using=self.SPARSE_VECTOR_NAME, limit=top_k),
            ]

            # Execute hybrid search
            results = await self.client.query_points(
                collection_name=collection_name,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                prefetch=prefetch_queries,
                limit=top_k,
                with_payload=True,
                search_params=models.SearchParams(
                    hnsw_ef=8,
                    exact=False,
                    quantization=models.QuantizationSearchParams(
                        ignore=False, rescore=True, oversampling=2.0
                    ),
                ),
            )

            documents = []
            for point in results.points:
                doc = {
                    "id": point.id,
                    "score": point.score,
                    "chunk_text": point.payload.get("chunk_text", ""),
                    "contextual_text": point.payload.get("contextual_text", ""),
                    "metadata": point.payload.get("metadata", {}),
                }
                documents.append(doc)

            search_duration = time.perf_counter() - start_query
            logger.info(f"🔍 Retrieved {len(documents)} results in {search_duration * 1000:.1f}ms")

            # Reranking
            if use_reranking and len(documents) > 1:
                rerank_start = time.perf_counter()

                if use_cohere and self.co:
                    logger.info(f"🔄 Reranking with Cohere ({cohere_model})...")
                    try:
                        rerank_results = self.co.rerank(
                            model=cohere_model,
                            query=query,
                            documents=[doc["chunk_text"] for doc in documents],
                            top_n=rerank_top_k,
                        )

                        reranked_docs = []
                        for item in rerank_results.results:
                            original_doc = documents[item.index].copy()
                            original_doc["rerank_score"] = float(item.relevance_score)
                            reranked_docs.append(original_doc)

                        documents = reranked_docs

                    except Exception as e:
                        logger.error(f"Cohere reranking failed: {e}")

                elif rerank_model:
                    logger.info(f"🔄 Reranking with {rerank_model}...")
                    try:
                        rerank_resp = await self.api_client.rerank_documents(
                            query=query,
                            documents=[doc["chunk_text"] for doc in documents],
                            model=rerank_model,
                            top_k=rerank_top_k,
                        )

                        reranked_docs = []
                        for item in rerank_resp:
                            original_doc = documents[item["index"]].copy()
                            original_doc["rerank_score"] = item["score"]
                            reranked_docs.append(original_doc)

                        documents = reranked_docs

                    except ServiceMaintenanceError:
                        raise

                    except Exception as e:
                        logger.error(f"Local reranking failed: {e}")

                rerank_duration = time.perf_counter() - rerank_start
                logger.info(f"🎯 Reranking completed in {rerank_duration:.2f}s")

            total_duration = time.perf_counter() - start_time
            logger.success(f"✅ Total time: {total_duration:.2f}s")

            return documents

        except ServiceMaintenanceError:
            raise

        except Exception as e:
            logger.error(f"Search failed: {e}")
            import traceback

            traceback.print_exc()
            return []

    def _parse_dense_embedding(self, response: Any) -> list[float]:
        """
        Parse dense embedding response dari API

        API Response format:
        - List[float]: [0.1, 0.2, ...] -> return as-is
        - Dict: {"embedding": [0.1, 0.2, ...]} -> extract

        Args:
            response: Response dari get_dense_embeddings

        Returns:
            List of floats
        """
        if isinstance(response, list):
            # Direct list format
            if isinstance(response[0], (int, float)):
                return response
            # List of embeddings [[...], [...]]
            elif isinstance(response[0], list):
                return response[0]
        elif isinstance(response, dict):
            # Dict format with 'embedding' key
            if "embedding" in response:
                return response["embedding"]
            # Dict format with 'data' key (OpenAI-style)
            elif "data" in response:
                return response["data"][0]["embedding"]

        logger.error(f"Unknown dense embedding format: {type(response)}")
        raise ValueError(f"Cannot parse dense embedding: {response}")

    def _parse_sparse_embedding(self, response: Any) -> dict[str, np.ndarray]:
        """
        Parse sparse embedding response from API and format for Qdrant

        API Response formats:
        1. List of dicts: [{"index": 123, "value": 0.5}, ...]
        2. Nested list [[{"index": 123, "value": 0.5}, ...]]

        Qdrant expects:
        {
            "indices": np.array([...], dtype=int32),
            "values": np.array([...], dtype=float32)
        }

        Args:
            response: Response from get_sparse_embeddings

        Returns:
            Dict with indices and values as numpy arrays
        """
        indices = []
        values = []

        # Format 1: List of dicts [{"index": 123, "value": 0.5}, ...]
        if isinstance(response, list):
            for item in response:
                if isinstance(item, dict):
                    # Handle both "index" and "indices"
                    idx = item.get("index") or item.get("indices")
                    val = item.get("value") or item.get("values")
                    if idx is not None and val is not None:
                        indices.append(idx)
                        values.append(val)

        # Format 2: Nested list [[{"index": 123, "value": 0.5}, ...]]
        elif isinstance(response, list) and response and isinstance(response[0], list):
            if response[0]:  # Ensure the inner list is not empty
                for item in response[0]:
                    if isinstance(item, dict):
                        idx = item.get("index")
                        val = item.get("value")
                        if idx is not None and val is not None:
                            indices.append(idx)
                            values.append(val)

        if not indices or not values:
            logger.warning("Empty sparse embedding, returning zeros")
            return {
                "indices": np.array([0], dtype=np.int32),
                "values": np.array([0.0], dtype=np.float32),
            }

        return {
            "indices": np.array(indices, dtype=np.int32),
            "values": np.array(values, dtype=np.float32),
        }

    def _format_sparse_for_qdrant(self, sparse_dict: dict[str, np.ndarray]) -> models.SparseVector:
        """
        Format sparse dict to Qdrant SparseVector object

        Args:
            sparse_dict: Dict with 'indices' and 'values' as numpy arrays

        Returns:
            models.SparseVector object
        """
        return models.SparseVector(
            indices=sparse_dict["indices"].tolist(), values=sparse_dict["values"].tolist()
        )

    async def get_info_collection(self, collection_name: str) -> dict[str, Any]:
        """
        Get collection information and statistics.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary containing collection information
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return {}

        try:
            info_collection = await self.client.get_collection(collection_name=collection_name)
            return info_collection.model_dump()
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}

    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection.

        Args:
            collection_name: Name of collection to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return False

        try:
            await self.client.delete_collection(collection_name)
            logger.success(f"Successfully deleted collection `{collection_name}`")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            return False

    async def count_documents(self, collection_name: str) -> int:
        """
        Count documents in collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Number of documents in collection
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return 0

        try:
            result = await self.client.count(collection_name)
            return result.count
        except Exception as e:
            logger.error(f"Error counting documents: {e}")
            return 0


_retriever_instance: QdrantVectoreStore | None = None


def get_retriever_instance() -> QdrantVectoreStore:
    """
    Get singleton instance of QdrantVectoreStore

    Returns:
        QdrantVectoreStore instance
    """
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = QdrantVectoreStore()
    return _retriever_instance
