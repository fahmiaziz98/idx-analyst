import asyncio
import time
from datetime import datetime
from typing import Any

import cohere
import numpy as np
from loguru import logger
from portalocker.exceptions import AlreadyLocked
from qdrant_client import AsyncQdrantClient, models
from tqdm import tqdm

from src.core import settings
from src.rag.inference import InferenceClient


class QdrantClientWrapper:
    """
    Enhanced wrapper class for Qdrant client with complete document information preservation.

    This wrapper handles both local and remote Qdrant instances and maintains all document
    metadata throughout the search and reranking pipeline.
    """

    def __init__(
        self,
        config=settings,
        path_client: str = "client",
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
        self.api_client = InferenceClient(
            base_url=config.EMBEDDING_API_URL, rerank_url=config.RERANK_API_URL
        )
        self.co = cohere.Client(self.config.COHERE_API_KEY)

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
            self.client = AsyncQdrantClient(
                url=self.config.QDRANT_BASE_URL,
                api_key=self.config.QDRANT_API_KEY,
                timeout=60,
                check_compatibility=False,
            )
            logger.success("Successfully created remote Qdrant client")

    async def init_collection(self):
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
            if not any(collection.name == self.config.COLLECTION for collection in existing):
                _ = await self.client.create_collection(
                    collection_name=self.config.COLLECTION,
                    vectors_config={
                        self.config.DENSE_VECTOR_NAME: models.VectorParams(
                            size=self.config.EMBEDDING_DENSE_SIZE, distance=models.Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        self.config.SPARSE_VECTOR_NAME: models.SparseVectorParams(
                            index=models.SparseIndexParams(on_disk=False),
                            modifier=models.Modifier.IDF,
                        )
                    },
                    hnsw_config=models.HnswConfigDiff(
                        on_disk=True,
                        ef_construct=64,
                        m=0,  # maximize performance speed indexing set = 0
                        payload_m=32,
                    ),
                    quantization_config=models.BinaryQuantization(
                        binary=models.BinaryQuantizationConfig(always_ram=True)
                    ),
                    optimizers_config=models.OptimizersConfigDiff(default_segment_number=32),
                )
                logger.success(f"Successfully created collection `{self.config.COLLECTION}`")
            else:
                logger.info(f"Collection `{self.config.COLLECTION}` already exists.")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")

    async def update_collection(
        self,
        hnsw_config: models.HnswConfigDiff | None = None,
        quantization_config: models.ScalarQuantization | None = None,
        optimizers_config: models.OptimizersConfigDiff | None = None,
    ) -> bool:
        """
        Update collection configuration.

        Args:
            collection_name: Name of collection to update
            hnsw_config: HNSW configuration updates
            quantization_config: Quantization configuration
            optimizers_config: Optimizer configuration

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return False

        kwargs = {}
        if hnsw_config:
            kwargs["hnsw_config"] = hnsw_config
        if quantization_config:
            kwargs["quantization_config"] = quantization_config
        if optimizers_config:
            kwargs["optimizers_config"] = optimizers_config

        try:
            await self.client.update_collection(collection_name=self.config.COLLECTION, **kwargs)
            logger.success(f"Successfully updated collection `{self.config.COLLECTION}`")
            return True
        except Exception as e:
            logger.error(f"Error updating collection: {e}")
            return False

    def _format_qdrant(self, embedding):
        "format sparse embedding for qdrant"
        indices_np = np.array(embedding["indices"])
        values_np = np.array(embedding["values"])
        return {
            "values": values_np,
            "indices": indices_np,
        }

    async def upload_collection(
        self, documents: list[dict[str, Any]], batch_size: int = 32
    ) -> dict[str, int]:
        """
        Upload documents to collection with batch processing.

        Args:
            documents: List of documents to upload
            batch_size: Batch size for processing

        Returns:
            Dictionary with success/failure counts
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return {"successful": 0, "failed": 0}

        successful_count = 0
        failed_count = 0

        for i in tqdm(range(0, len(documents), batch_size), desc="Uploading document batches"):
            batch = documents[i : i + batch_size]
            points = []

            for doc in batch:
                if not doc.get("id"):
                    logger.warning(f"Document at index {i} has no ID, skipping")
                    failed_count += 1
                    continue

                try:
                    text = doc.get("contextual_text")

                    dense_embeddings_coro = self.api_client.embed(
                        text=text,
                        model_id=self.config.EMBEDDING_DENSE,
                        prompt=self.config.INSTRUCTION_DOC,
                    )
                    sparse_embeddings_coro = self.api_client.embed(
                        text=text,
                        model_id=self.config.EMBEDDING_SPARSE,
                    )
                    dense_response, sparse_response = await asyncio.gather(
                        dense_embeddings_coro, sparse_embeddings_coro
                    )

                    dense_embeddings = dense_response.get("embedding", [])
                    sparse_embeddings = sparse_response.get("sparse_embedding", [])

                    vectors = {
                        self.config.DENSE_VECTOR_NAME: dense_embeddings,
                        self.config.SPARSE_VECTOR_NAME: self._format_qdrant(sparse_embeddings),
                    }

                    point = models.PointStruct(
                        id=doc.get("id"),
                        vector=vectors,
                        payload={
                            "id": doc.get("id"),
                            "chunk_text": doc.get("chunk_text", ""),
                            "metadata": doc.get("metadata", {}),
                            "upload_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        },
                    )
                    points.append(point)

                except Exception as e:
                    logger.error(f"Failed to process document {doc.get('id')}: {e}")
                    failed_count += 1
                    continue

            if points:
                try:
                    await self.client.upsert(
                        collection_name=self.config.COLLECTION,
                        points=points,
                    )
                    successful_count += len(points)

                except Exception as e:
                    logger.error(f"Failed to upload batch: {e}")
                    failed_count += len(points)

        logger.success(
            f"Upload complete: {successful_count} succeeded, {failed_count} failed to `{self.config.COLLECTION}`"
        )

        # Update HNSW configuration
        logger.info("Update hnsw config...")
        try:
            await self.update_collection(
                hnsw_config=models.HnswConfigDiff(on_disk=True, ef_construct=64, m=32, payload_m=32)
            )
        except Exception as e:
            logger.error(f"Failed to update collection configuration: {e}")

        return {"successful": successful_count, "failed": failed_count}

    async def search(
        self,
        query: str,
        using_cohere: bool = False,
        prefetch_limit: int = 20,
        limit_reranker: int = 5,
        use_reranking: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search documents with hybrid retrieval and optional reranking.

        Args:
            query: Search query text
            collection_name: Name of collection to search
            using_cohere: Whether to use Cohere for reranking
            prefetch_limit: Number of documents to retrieve initially
            limit_reranker: Number of documents to return after reranking
            use_reranking: Whether to apply reranking

        Returns:
            List of documents with complete information (id, score, text, metadata)
        """
        if not self.client:
            logger.error("Qdrant client not available")
            return []

        try:
            start_time = time.perf_counter()

            dense_query_coro = self.api_client.query(
                text=query,
                model_id=self.config.EMBEDDING_DENSE,
                prompt=self.config.INSTRUCTION_QUERY,
            )
            sparse_query_coro = self.api_client.query(
                text=query,
                model_id=self.config.EMBEDDING_SPARSE,
            )
            dense_query, sparse_query_raw = await asyncio.gather(
                dense_query_coro, sparse_query_coro
            )
            sparse_embedding = sparse_query_raw.get("sparse_embedding", [])
            sparse_query = self._format_qdrant(sparse_embedding)

            prefetch_query = [
                models.Prefetch(
                    query=np.array(dense_query["embedding"], dtype=np.float32),
                    using=self.config.DENSE_VECTOR_NAME,
                    limit=prefetch_limit,
                ),
                models.Prefetch(
                    query=models.SparseVector(**sparse_query),
                    using=self.config.SPARSE_VECTOR_NAME,
                    limit=prefetch_limit,
                ),
            ]

            # Execute hybrid search
            results = await self.client.query_points(
                collection_name=self.config.COLLECTION,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                prefetch=prefetch_query,
                limit=prefetch_limit,
                with_payload=True,
                search_params=models.SearchParams(
                    quantization=models.QuantizationSearchParams(
                        ignore=False,
                        rescore=True,  # Enables rescoring with original vectors
                        oversampling=2,  # Retrieves extra candidates for rescoring
                    )
                ),
            )

            document_list = []
            for point in results.points:
                doc = {
                    "id": point.id,
                    "score": point.score,
                    "chunk_text": point.payload.get("chunk_text", ""),
                    "metadata": point.payload.get("metadata", {}),
                }
                document_list.append(doc)

            search_duration = time.perf_counter() - start_time
            logger.info(
                f"🔍 Retrieved {len(document_list)} results in {search_duration:.2f} seconds"
            )

            if use_reranking and len(document_list) > 1:
                rerank_start = time.perf_counter()

                if using_cohere:
                    logger.info(f"🔄 Reranking {len(document_list)} documents using Cohere...")

                    try:
                        rerank_results = self.co.rerank(
                            model=self.config.COHERE_RANKER_MODEL,
                            query=query,
                            documents=[doc["chunk_text"] for doc in document_list],
                            top_n=limit_reranker,
                        )

                        reranked_documents = []
                        for item in rerank_results.results:
                            original_doc = document_list[item.index].copy()
                            original_doc["rerank_score"] = float(item.relevance_score)
                            reranked_documents.append(original_doc)

                    except Exception as e:
                        logger.error(f"Cohere reranking failed: {e}")
                        reranked_documents = document_list

                else:
                    logger.info(
                        f"🔄 Reranking {len(document_list)} documents using {self.config.QWEN3_RANK}..."
                    )

                    try:
                        texts = [doc["chunk_text"] for doc in document_list]

                        rerank_response = await self.api_client.rerank(
                            query=query,
                            documents=texts,
                            model_id=self.config.QWEN3_RANK,
                            prompt=self.config.INSTRUCTION_RERANK,
                            top_k=limit_reranker,
                        )

                        reranked_documents = []
                        for rerank_result in rerank_response["results"]:
                            original_doc = document_list[rerank_result["index"]].copy()
                            original_doc["rerank_score"] = rerank_result["score"]
                            reranked_documents.append(original_doc)

                    except Exception as e:
                        logger.error(f"Local reranking failed: {e}")
                        reranked_documents = document_list

                rerank_duration = time.perf_counter() - rerank_start
                logger.info(f"🎯 Reranking completed in {rerank_duration:.2f} seconds")

                return reranked_documents

            else:
                return document_list

        except Exception as e:
            logger.error(f"Error during query: {e}")
            return []

    async def get_info_collection(self) -> dict[str, Any]:
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
            info_collection = await self.client.get_collection(
                collection_name=self.config.COLLECTION
            )
            return info_collection.model_dump()
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}

    async def delete_collection(self) -> bool:
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
            await self.client.delete_collection(self.config.COLLECTION)
            logger.success(f"Successfully deleted collection `{self.config.COLLECTION}`")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            return False

    async def count_documents(self) -> int:
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
            result = await self.client.count(self.config.COLLECTION)
            return result.count
        except Exception as e:
            logger.error(f"Error counting documents: {e}")
            return 0


_retriever_instance: QdrantClientWrapper | None = None


def get_retriever_instance() -> QdrantClientWrapper:
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = QdrantClientWrapper()
    return _retriever_instance
