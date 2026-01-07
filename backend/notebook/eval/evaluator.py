import asyncio
import time
from dataclasses import dataclass
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from loguru import logger

# Configure plotting style
sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["font.size"] = 10


@dataclass
class EvaluationResult:
    """Container for single query evaluation result"""

    query_id: str
    query: str
    ground_truth_id: str
    retrieved_ids: list[str]
    scores: list[float]
    hit: int
    mrr: float
    ndcg: float
    rank: int | None
    latency_ms: float


class RAGEvaluator:
    """
    Comprehensive RAG Retrieval Evaluator

    Metrics:
    - Hit Rate@K: Success rate in finding relevant doc
    - MRR: Mean Reciprocal Rank (position-aware)
    - NDCG@K: Normalized Discounted Cumulative Gain (ranking quality)
    """

    def __init__(self):
        self.results: list[EvaluationResult] = []

    @staticmethod
    def calculate_hit_rate(retrieved_ids: list[str], ground_truth_id: str) -> int:
        """
        Calculate hit (1) or miss (0)

        Args:
            retrieved_ids: List of retrieved document IDs
            ground_truth_id: Ground truth document ID

        Returns:
            1 if hit, 0 if miss
        """
        return 1 if ground_truth_id in retrieved_ids else 0

    @staticmethod
    def calculate_mrr(retrieved_ids: list[str], ground_truth_id: str) -> tuple[float, int | None]:
        """
        Calculate Mean Reciprocal Rank

        Args:
            retrieved_ids: List of retrieved document IDs
            ground_truth_id: Ground truth document ID

        Returns:
            (mrr_score, rank) - rank is None if not found
        """
        try:
            rank = retrieved_ids.index(ground_truth_id) + 1
            return 1.0 / rank, rank
        except ValueError:
            return 0.0, None

    @staticmethod
    def calculate_ndcg(
        retrieved_ids: list[str], ground_truth_id: str, k: int | None = None
    ) -> float:
        """
        Calculate NDCG@K (Normalized Discounted Cumulative Gain)

        For binary relevance (single ground truth):
        - Relevant doc gets score 1, others get 0
        - DCG uses log2(rank+1) discount

        Args:
            retrieved_ids: List of retrieved document IDs
            ground_truth_id: Ground truth document ID
            k: Cut-off (if None, use all retrieved)

        Returns:
            NDCG score (0.0 to 1.0)
        """
        if k is not None:
            retrieved_ids = retrieved_ids[:k]

        # DCG calculation
        dcg = 0.0
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id == ground_truth_id:
                # Relevance = 1 for ground truth, 0 for others
                # Discount = log2(position + 1)
                rank = i + 1
                dcg = 1.0 / np.log2(rank + 1)
                break

        # IDCG (Ideal DCG) - best possible DCG
        # For single ground truth, ideal is having it at rank 1
        idcg = 1.0 / np.log2(2)  # log2(1 + 1) = log2(2)

        # NDCG
        if idcg == 0:
            return 0.0

        return dcg / idcg

    async def evaluate_query(
        self,
        query_data: dict[str, Any],
        vector_store,
        collection_name: str,
        dense_model: str,
        sparse_model: str,
        dense_instruction: str | None = None,
        top_k: int = 10,
        use_reranking: bool = False,
        **search_kwargs,
    ) -> EvaluationResult:
        """
        Evaluate single query

        Args:
            query_data: Dict with keys: 'id', 'question', 'answer', 'context'
            vector_store: QdrantVectorStore instance
            collection_name: Collection name
            dense_model: Dense embedding model
            sparse_model: Sparse embedding model
            dense_instruction: Embedding instruction
            top_k: Number of results to retrieve
            performance_mode: "speed", "balanced", or "accuracy"
            use_reranking: Whether to use reranking
            **search_kwargs: Additional search parameters

        Returns:
            EvaluationResult object
        """
        query_id = query_data["id"]
        query = query_data["question"]
        ground_truth_id = int(query_data["id"])

        # Measure latency
        start_time = time.perf_counter()

        try:
            # Perform search
            results = await vector_store.search(
                query=query,
                collection_name=collection_name,
                dense_model=dense_model,
                sparse_model=sparse_model,
                dense_instruction=dense_instruction,
                top_k=top_k,
                use_reranking=use_reranking,
                **search_kwargs,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Extract IDs and scores
            retrieved_ids = [r["id"] for r in results]
            scores = [r.get("score", 0.0) for r in results]

            # Calculate metrics
            hit = self.calculate_hit_rate(retrieved_ids, ground_truth_id)
            mrr, rank = self.calculate_mrr(retrieved_ids, ground_truth_id)
            ndcg = self.calculate_ndcg(retrieved_ids, ground_truth_id, k=top_k)

            result = EvaluationResult(
                query_id=query_id,
                query=query,
                ground_truth_id=ground_truth_id,
                retrieved_ids=retrieved_ids,
                scores=scores,
                hit=hit,
                mrr=mrr,
                ndcg=ndcg,
                rank=rank,
                latency_ms=latency_ms,
            )

            return result

        except Exception as e:
            logger.error(f"Error evaluating query {query_id}: {e}")

            # Return zero metrics on error
            return EvaluationResult(
                query_id=query_id,
                query=query,
                ground_truth_id=ground_truth_id,
                retrieved_ids=[],
                scores=[],
                hit=0,
                mrr=0.0,
                ndcg=0.0,
                rank=None,
                latency_ms=0.0,
            )

    async def evaluate_dataset(
        self,
        eval_dataset: list[dict[str, Any]],
        vector_store,
        collection_name: str,
        dense_model: str,
        sparse_model: str,
        dense_instruction: str | None = None,
        top_k: int = 10,
        use_reranking: bool = False,
        verbose: bool = True,
        **search_kwargs,
    ) -> pd.DataFrame:
        """
        Evaluate entire dataset

        Args:
            eval_dataset: List of eval data [{'id', 'question', 'answer', 'context'}, ...]
            vector_store: QdrantVectorStore instance
            collection_name: Collection name
            dense_model: Dense model ID
            sparse_model: Sparse model ID
            dense_instruction: Embedding instruction
            top_k: Top-K for retrieval
            performance_mode: Performance mode
            use_reranking: Use reranking
            verbose: Print progress
            **search_kwargs: Additional search parameters

        Returns:
            DataFrame with detailed results
        """
        self.results = []  # Reset

        total = len(eval_dataset)

        logger.info(f"\n{'=' * 70}")
        logger.info("🧪 STARTING EVALUATION")
        logger.info(f"{'=' * 70}")
        logger.info(f"Dataset size: {total} queries")
        logger.info(f"Top-K: {top_k}")
        logger.info(f"Reranking: {use_reranking}")
        logger.info(f"{'=' * 70}\n")

        # Evaluate each query
        for i, query_data in enumerate(eval_dataset, 1):
            if verbose:
                logger.info(f"[{i}/{total}] Evaluating: {query_data['question'][:60]}...")

            # ⏳ Cohere rate limit: delay setiap 10 query
            if use_reranking and search_kwargs.get("use_cohere", False) and i % 10 == 0 and i > 0:
                if verbose:
                    logger.warning("⏳ Cohere rate limit: waiting 65 seconds...")
                await asyncio.sleep(65)

            result = await self.evaluate_query(
                query_data=query_data,
                vector_store=vector_store,
                collection_name=collection_name,
                dense_model=dense_model,
                sparse_model=sparse_model,
                dense_instruction=dense_instruction,
                top_k=top_k,
                use_reranking=use_reranking,
                **search_kwargs,
            )

            self.results.append(result)

            if verbose:
                status = "✅ HIT" if result.hit else "❌ MISS"
                logger.info(
                    f"   {status} | MRR: {result.mrr:.3f} | NDCG: {result.ndcg:.3f} | "
                    f"Latency: {result.latency_ms:.1f}ms"
                )
                if result.rank:
                    logger.info(f"   📍 Found at rank {result.rank}")
                logger.info("")

        # Convert to DataFrame
        df = self.to_dataframe()

        return df

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert results to pandas DataFrame

        Returns:
            DataFrame with columns: query_id, query, hit, mrr, ndcg, rank, latency_ms
        """
        data = []
        for result in self.results:
            data.append(
                {
                    "query_id": result.query_id,
                    "query": result.query,
                    "ground_truth_id": result.ground_truth_id,
                    "hit": result.hit,
                    "mrr": result.mrr,
                    "ndcg": result.ndcg,
                    "rank": result.rank if result.rank else np.nan,
                    "latency_ms": result.latency_ms,
                    "num_retrieved": len(result.retrieved_ids),
                }
            )

        return pd.DataFrame(data)

    def calculate_aggregate_metrics(self, k_values: list[int] = [3, 5, 10, 20]) -> dict[str, Any]:
        """
        Calculate aggregate metrics across all queries

        Args:
            k_values: Different K values for Hit Rate@K

        Returns:
            Dictionary with aggregate metrics
        """
        if not self.results:
            logger.warning("No results to aggregate")
            return {}

        total_queries = len(self.results)

        # Basic metrics
        hit_rate = sum(r.hit for r in self.results) / total_queries
        mean_mrr = sum(r.mrr for r in self.results) / total_queries
        mean_ndcg = sum(r.ndcg for r in self.results) / total_queries

        # Latency metrics
        latencies = [r.latency_ms for r in self.results]
        mean_latency = np.mean(latencies)
        p50_latency = np.percentile(latencies, 50)
        p95_latency = np.percentile(latencies, 95)
        p99_latency = np.percentile(latencies, 99)

        # Hit Rate at different K values
        hit_rates_at_k = {}
        for k in k_values:
            hits_at_k = sum(1 for r in self.results if r.ground_truth_id in r.retrieved_ids[:k])
            hit_rates_at_k[f"hit_rate@{k}"] = hits_at_k / total_queries

        # Rank distribution
        ranks = [r.rank for r in self.results if r.rank is not None]
        rank_distribution = {}
        if ranks:
            rank_distribution = {
                "mean_rank": np.mean(ranks),
                "median_rank": np.median(ranks),
                "min_rank": min(ranks),
                "max_rank": max(ranks),
            }

        aggregate = {
            "total_queries": total_queries,
            "hits": sum(r.hit for r in self.results),
            "misses": total_queries - sum(r.hit for r in self.results),
            "hit_rate": hit_rate,
            "mean_mrr": mean_mrr,
            "mean_ndcg": mean_ndcg,
            **hit_rates_at_k,
            "mean_latency_ms": mean_latency,
            "p50_latency_ms": p50_latency,
            "p95_latency_ms": p95_latency,
            "p99_latency_ms": p99_latency,
            **rank_distribution,
        }

        return aggregate

    def print_summary(self, aggregate_metrics: dict[str, Any]):
        """
        Print formatted summary of evaluation results

        Args:
            aggregate_metrics: Dictionary from calculate_aggregate_metrics()
        """
        print(f"\n{'=' * 70}")
        print("📊 EVALUATION SUMMARY")
        print(f"{'=' * 70}\n")

        print("Dataset Overview:")
        print(f"  • Total Queries: {aggregate_metrics['total_queries']}")
        print(f"  • Hits: {aggregate_metrics['hits']}")
        print(f"  • Misses: {aggregate_metrics['misses']}")

        print("\nPrimary Metrics:")
        print(f"  • Hit Rate@10: {aggregate_metrics['hit_rate']:.2%}")
        print(f"  • Mean MRR: {aggregate_metrics['mean_mrr']:.4f}")
        print(f"  • Mean NDCG@10: {aggregate_metrics['mean_ndcg']:.4f}")

        print("\nHit Rate at Different K:")
        for k in [3, 5, 10, 20]:
            key = f"hit_rate@{k}"
            if key in aggregate_metrics:
                print(f"  • Hit Rate@{k}: {aggregate_metrics[key]:.2%}")

        if "mean_rank" in aggregate_metrics:
            print("\nRank Statistics (for hits):")
            print(f"  • Mean Rank: {aggregate_metrics['mean_rank']:.2f}")
            print(f"  • Median Rank: {aggregate_metrics['median_rank']:.1f}")
            print(f"  • Best Rank: {aggregate_metrics['min_rank']}")
            print(f"  • Worst Rank: {aggregate_metrics['max_rank']}")

        print("\nLatency Statistics:")
        print(f"  • Mean: {aggregate_metrics['mean_latency_ms']:.1f}ms")
        print(f"  • P50: {aggregate_metrics['p50_latency_ms']:.1f}ms")
        print(f"  • P95: {aggregate_metrics['p95_latency_ms']:.1f}ms")
        print(f"  • P99: {aggregate_metrics['p99_latency_ms']:.1f}ms")

        print(f"\n{'=' * 70}\n")

    def plot_results(
        self,
        name: str,
        aggregate_metrics: dict[str, Any],
        df: pd.DataFrame,
        save_path: str | None = None,
    ):
        """
        Create comprehensive visualization of evaluation results

        Args:
            aggregate_metrics: Aggregate metrics dictionary
            df: Results DataFrame
            save_path: Optional path to save figure
        """
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"Evaluation Results {name}", fontsize=16, fontweight="bold")

        # 1. Hit Rate at Different K
        ax1 = axes[0, 0]
        k_values = [3, 5, 10, 20]
        hit_rates = [aggregate_metrics.get(f"hit_rate@{k}", 0) * 100 for k in k_values]

        bars1 = ax1.bar(range(len(k_values)), hit_rates, color="steelblue", alpha=0.8)
        ax1.set_xlabel("Top-K", fontweight="bold")
        ax1.set_ylabel("Hit Rate (%)", fontweight="bold")
        ax1.set_title("Hit Rate@K", fontweight="bold")
        ax1.set_xticks(range(len(k_values)))
        ax1.set_xticklabels([f"@{k}" for k in k_values])
        ax1.set_ylim([0, 105])
        ax1.grid(axis="y", alpha=0.3)

        # Add value labels on bars
        for bar in bars1:
            height = bar.get_height()
            ax1.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{height:.1f}%",
                ha="center",
                va="bottom",
                fontweight="bold",
            )

        # 2. Primary Metrics Comparison
        ax2 = axes[0, 1]
        metrics = ["Hit Rate", "MRR", "NDCG"]
        values = [
            aggregate_metrics["hit_rate"] * 100,
            aggregate_metrics["mean_mrr"] * 100,
            aggregate_metrics["mean_ndcg"] * 100,
        ]

        bars2 = ax2.bar(metrics, values, color=["#2ecc71", "#3498db", "#e74c3c"], alpha=0.8)
        ax2.set_ylabel("Score (%)", fontweight="bold")
        ax2.set_title("Primary Metrics Comparison", fontweight="bold")
        ax2.set_ylim([0, 105])
        ax2.grid(axis="y", alpha=0.3)

        for bar in bars2:
            height = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{height:.1f}%",
                ha="center",
                va="bottom",
                fontweight="bold",
            )

        # 3. Rank Distribution (for hits only)
        ax3 = axes[0, 2]
        ranks = df[df["hit"] == 1]["rank"].dropna()

        if len(ranks) > 0:
            ax3.hist(
                ranks,
                bins=range(1, int(ranks.max()) + 2),
                color="coral",
                alpha=0.7,
                edgecolor="black",
            )
            ax3.set_xlabel("Rank Position", fontweight="bold")
            ax3.set_ylabel("Frequency", fontweight="bold")
            ax3.set_title("Rank Distribution (Hits Only)", fontweight="bold")
            ax3.grid(axis="y", alpha=0.3)

            # Add mean line
            mean_rank = ranks.mean()
            ax3.axvline(
                mean_rank, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_rank:.2f}"
            )
            ax3.legend()
        else:
            ax3.text(
                0.5, 0.5, "No hits to display", ha="center", va="center", transform=ax3.transAxes
            )

        # 4. Latency Distribution
        ax4 = axes[1, 0]
        latencies = df["latency_ms"].dropna()

        ax4.hist(latencies, bins=30, color="purple", alpha=0.7, edgecolor="black")
        ax4.set_xlabel("Latency (ms)", fontweight="bold")
        ax4.set_ylabel("Frequency", fontweight="bold")
        ax4.set_title("Latency Distribution", fontweight="bold")
        ax4.grid(axis="y", alpha=0.3)

        # Add percentile lines
        p50 = aggregate_metrics["p50_latency_ms"]
        p95 = aggregate_metrics["p95_latency_ms"]
        ax4.axvline(p50, color="green", linestyle="--", linewidth=2, label=f"P50: {p50:.1f}ms")
        ax4.axvline(p95, color="red", linestyle="--", linewidth=2, label=f"P95: {p95:.1f}ms")
        ax4.legend()

        # 5. Hit vs Miss Pie Chart
        ax5 = axes[1, 1]
        hits = aggregate_metrics["hits"]
        misses = aggregate_metrics["misses"]

        colors = ["#2ecc71", "#e74c3c"]
        explode = (0.05, 0)
        ax5.pie(
            [hits, misses],
            labels=["Hits", "Misses"],
            autopct="%1.1f%%",
            colors=colors,
            explode=explode,
            startangle=90,
            textprops={"fontweight": "bold", "fontsize": 12},
        )
        ax5.set_title("Hit vs Miss Distribution", fontweight="bold")

        # 6. MRR vs NDCG Scatter
        ax6 = axes[1, 2]
        ax6.scatter(df["mrr"], df["ndcg"], alpha=0.6, s=50, color="teal")
        ax6.set_xlabel("MRR", fontweight="bold")
        ax6.set_ylabel("NDCG@10", fontweight="bold")
        ax6.set_title("MRR vs NDCG Correlation", fontweight="bold")
        ax6.grid(True, alpha=0.3)

        # Add diagonal reference line
        max_val = max(df["mrr"].max(), df["ndcg"].max())
        ax6.plot([0, max_val], [0, max_val], "r--", alpha=0.5, label="Perfect correlation")
        ax6.legend()

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            logger.info(f"📊 Plot saved to: {save_path}")

        plt.show()
