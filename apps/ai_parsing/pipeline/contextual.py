import asyncio
from typing import Any

from loguru import logger

from ..core.exception import ContextualizationError, ValidationError
from .prompt import SYSTEM_PROMPT, TABLE_PROMPT
from ..rag.llm_client import VLMClient
from ..utils.timing import Timer

RETRY_DELAY = 1.0  # Seconds between retries


class TableContextualizer:
    """
    LLM-based contextualizer for financial tables.

    This class handles:
    - Context generation specifically for tables
    - Retry logic with exponential backoff for failed API calls
    - Batch processing of document chunks

    Only tables are contextualized (not text/headers) to reduce API costs
    and focus on structured financial data which benefits most from context.

    Attributes:
        client: VLM client instance for LLM inference.
        model: LLM model name.
        max_retries: Maximum retry attempts for failed calls.
    """

    def __init__(
        self,
        model: str = "Qwen3-VL",
        temperature: float = 1.0,
        max_tokens: int = 4096,
        min_p: float = 0.1,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize the table contextualizer.

        Args:
            model: LLM model name. Defaults to "Qwen3-VL".
            temperature: LLM sampling temperature. Defaults to 1.0.
            max_tokens: Maximum tokens for generation. Defaults to 4096.
            min_p: Minimum probability for nucleus sampling. Defaults to 0.1.
            max_retries: Max retry attempts for failed API calls. Defaults to 3.

        Raises:
            ValidationError: If VLMClient initialization fails.
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.min_p = min_p
        self.max_retries = max_retries
        self.system_prompt = SYSTEM_PROMPT
        self.user_prompt = TABLE_PROMPT

        try:
            self.client = VLMClient(
                model_name=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                min_p=self.min_p,
            )
            logger.info(f"Initialized contextualizer with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize VLM client: {e}")
            raise ValidationError(f"Failed to initialize VLM client: {e}") from e

    async def contextualize_table(
        self, table_text: str, full_document: str, retry_count: int = 0
    ) -> str:
        """
        Generate contextual information for a financial table.

        Uses LLM to analyze the table in the context of the full document
        and generate a summary with key financial metrics.

        Args:
            table_text: The table content (markdown format).
            full_document: Full document text for context.
            retry_count: Current retry attempt (internal use).

        Returns:
            Contextualized description of the table.

        Raises:
            ContextualizationError: If generation fails or result is too short.
        """
        if not table_text.strip():
            raise ContextualizationError("Empty table text provided")

        try:
            # Format prompt
            user_message = self.user_prompt.format(
                chunk=table_text, document=full_document
            )

            # Call LLM
            logger.debug(f"Calling {self.model} for table contextualization")
            with Timer() as t:
                response = await self.client.generate(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_message},
                    ]
                )

            if not response or len(response) < 50:
                raise ContextualizationError(
                    f"Generated context too short: {len(response)} chars"
                )

            logger.info(f"Generated {len(response)} chars of context in {t.elapsed_str}")
            return response

        except ContextualizationError:
            raise
        except Exception as e:
            # Retry logic with exponential backoff
            if retry_count < self.max_retries:
                wait_time = RETRY_DELAY * (retry_count + 1)
                logger.warning(
                    f"Contextualization failed (attempt {retry_count + 1}/"
                    f"{self.max_retries}), retrying in {wait_time}s: {e}"
                )
                await asyncio.sleep(wait_time)
                return await self.contextualize_table(
                    table_text, full_document, retry_count + 1
                )

            error_msg = f"Failed to contextualize table after {self.max_retries} retries: {e}"
            logger.error(error_msg)
            raise ContextualizationError(error_msg) from e

    async def contextualize_batch(
        self,
        chunks: list[dict[str, Any]],
        full_document: str,
        show_progress: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Contextualize multiple chunks (tables only).

        Args:
            chunks: List of chunk dictionaries (must have "content" and "type" keys).
            full_document: Full document text for context.
            show_progress: Whether to show progress logs.

        Returns:
            List of chunks with 'contextualized_content' field added.
        """
        if not chunks:
            raise ContextualizationError("No chunks provided for contextualization")

        # Count tables for logging
        table_chunks = [c for c in chunks if c.get("type") == "table"]
        table_count = len(table_chunks)

        logger.info(
            f"Contextualizing {table_count} tables out of {len(chunks)} total chunks"
        )

        processed_tables = 0
        failed_tables = 0

        for i, chunk in enumerate(chunks, 1):
            chunk_type = chunk.get("type", "text")
            content = chunk.get("content", "")

            if chunk_type == "table":
                try:
                    processed_tables += 1
                    if show_progress:
                        logger.info(
                            f"Processing table {processed_tables}/{table_count}..."
                        )

                    contextualized = await self.contextualize_table(
                        content, full_document
                    )
                    chunk["contextualized_content"] = contextualized

                except Exception as e:
                    logger.error(f"Failed to contextualize table chunk {i}: {e}")
                    chunk["contextualized_content"] = content  # Fallback
                    failed_tables += 1
            else:
                # Non-table content is passed through unchanged
                chunk["contextualized_content"] = content

        # Summary logging
        if table_count > 0:
            success_count = processed_tables - failed_tables
            success_rate = (success_count / table_count) * 100
            logger.success(
                f"Contextualization complete: {success_count}/{table_count} tables "
                f"succeeded ({success_rate:.1f}%)"
            )
            if failed_tables > 0:
                logger.warning(f"{failed_tables} tables failed (using original content)")

        return chunks

    async def close(self) -> None:
        """Close the underlying VLM client connection."""
        if hasattr(self.client, "client"):
            await self.client.client.close()
        logger.debug("Contextualizer client closed")


class NoOpContextualizer:
    """
    No-op contextualizer that returns original content unchanged.
    """

    def __init__(self) -> None:
        logger.info("Using no-op contextualizer (contextualization disabled)")

    async def contextualize_table(
        self, table_text: str, full_document: str, **kwargs: Any
    ) -> str:
        """Pass through content unchanged."""
        return table_text

    async def contextualize_batch(
        self, chunks: list[dict[str, Any]], full_document: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Pass through all chunks unchanged."""
        for chunk in chunks:
            chunk["contextualized_content"] = chunk.get("content", "")
        return chunks

    async def close(self) -> None:
        """No resources to close."""
        pass
