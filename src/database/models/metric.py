from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from src.database.models.message import Message


class Metric(Base):
    """
    Metric model for tracking latency and performance metrics

    Track latency:
    - LLM response generation
    - Embedding generation
    - Vector database query
    - Total request latency

    Example:
        metric = Metric(
            message_id="msg-123",
            llm_latency_ms=850.5,
            embedding_latency_ms=120.3,
            vector_query_latency_ms=45.2,
            total_latency_ms=1015.0
        )
    """

    __tablename__ = "metrics"

    # Foreign Key
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Message track (optional)",
    )

    # ===== Latency Metrics (in milliseconds) =====

    llm_latency_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Latency LLM response generation (ms)"
    )

    embedding_latency_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Latency embedding generation (ms)"
    )

    vector_query_latency_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Latency vector database query (ms)"
    )

    total_latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        index=True,  # Index untuk query average latency
        comment="Total request latency (ms)",
    )

    # Relationships
    # One metric belongs to one message
    message: Mapped[Optional["Message"]] = relationship(
        "Message", back_populates="metric", lazy="joined"
    )

    def __repr__(self) -> str:
        """Pretty print debugging."""
        return (
            f"<Metric(total={self.total_latency_ms:.2f}ms, "
            f"llm={self.llm_latency_ms:.2f}ms, "
            f"cache_hit={self.cache_hit})>"
        )

    @property
    def is_slow(self) -> bool:
        """
        Helper property untuk detect slow requests.
        Threshold: > 5000ms (5 seconds)
        """
        return self.total_latency_ms > 5000

    def to_dict(self) -> dict:
        """
        Convert metric ke dictionary untuk API response.

        Returns:
            dict: Metric data dalam format JSON-friendly
        """
        return {
            "llm_latency_ms": self.llm_latency_ms,
            "embedding_latency_ms": self.embedding_latency_ms,
            "vector_query_latency_ms": self.vector_query_latency_ms,
            "total_latency_ms": self.total_latency_ms,
        }
