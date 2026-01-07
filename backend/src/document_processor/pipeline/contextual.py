import asyncio

from loguru import logger
from openai import AsyncOpenAI

from src.core.exception import ContextualizationError, ValidationError
from src.document_processor.pipeline.prompt import SYSTEM_PROMPT, TABLE_PROMPT

RETRY_DELAY = 1.0  # Seconds between retries


class TableContextualizer:
    """
    LLM-based contextualizer for financial tables.

    This class handles:
    - OpenAI-compatible API integration (Groq, OpenRouter, etc.)
    - Rate limiting between requests
    - Retry logic for failed API calls
    - Context generation specifically for tables

    Only tables are contextualized (not text/headers) to reduce API costs
    and focus on structured financial data.

    Attributes:
        client: Async OpenAI client
        model: LLM model name
        delay: Seconds to wait between API calls
        max_retries: Maximum retry attempts for failed calls
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "moonshotai/kimi-k2-instruct-0905",
        delay: float = 2,
        max_retries: int = 3,
    ):
        """
        Initialize the table contextualizer.

        Args:
            api_key: OpenAI-compatible API key
            base_url: API base URL (default: Groq endpoint)
            model: Model name (default: deepseek-chat via Groq)
            delay: Seconds between API calls (default: 2.0)
            max_retries: Max retry attempts (default: 3)

        Raises:
            ValidationError: If client initialization fails
        """
        if not api_key:
            raise ValidationError("API key is required for contextualization")

        self.model = model
        self.delay = delay
        self.max_retries = max_retries
        self.SYSTEM_PROMPT = SYSTEM_PROMPT
        self.USER_PROMPT = TABLE_PROMPT

        try:
            # Use async client for better performance
            self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            logger.info(f"Initialized contextualizer with model: {model}")
            logger.debug(f"API endpoint: {base_url}")

        except Exception as e:
            raise ValidationError(f"Failed to initialize OpenAI client: {str(e)}") from e

    async def contextualize_table(
        self, table_text: str, full_document: str, retry_count: int = 0
    ) -> str:
        """
        Generate contextual information for a financial table.

        Uses LLM to analyze the table in context of the full document
        and generate a 4-6 sentence summary with key financial metrics.

        Args:
            table_text: The table content (markdown format)
            full_document: Full document text for context
            retry_count: Current retry attempt (internal use)

        Returns:
            Contextualized text describing the table

        Raises:
            ContextualizationError: If contextualization fails after retries
            APIError: If API call fails
        """
        if not table_text.strip():
            raise ContextualizationError("Empty table text provided")

        try:
            # Format prompt
            user_message = self.USER_PROMPT.format(chunk=table_text, document=full_document)

            # Call LLM
            logger.debug(f"Calling {self.model} for table contextualization")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                max_tokens=4096,
            )

            # Extract content
            contextualized = response.choices[0].message.content

            if not contextualized or len(contextualized.strip()) < 50:
                raise ContextualizationError(
                    f"Generated context too short: {len(contextualized)} chars"
                )

            logger.debug(f"Generated {len(contextualized)} chars of context")

            # Rate limiting
            await asyncio.sleep(self.delay)

            return contextualized.strip()

        except ContextualizationError:
            raise

        except Exception as e:
            # Retry logic
            if retry_count < self.max_retries:
                logger.warning(
                    f"Contextualization failed (attempt {retry_count + 1}/{self.max_retries}): {e}"
                )
                await asyncio.sleep(RETRY_DELAY * (retry_count + 1))  # Exponential backoff

                return await self.contextualize_table(table_text, full_document, retry_count + 1)
            else:
                # Max retries exceeded
                error_msg = f"Failed after {self.max_retries} retries: {str(e)}"
                logger.error(error_msg)
                raise ContextualizationError(error_msg) from e

    async def contextualize_batch(
        self, chunks: list, full_document: str, show_progress: bool = True
    ) -> list:
        """
        Contextualize multiple chunks (tables only).

        Processes chunks sequentially with rate limiting.
        Only tables are contextualized; text chunks are passed through unchanged.

        Args:
            chunks: List of chunk dictionaries (must have "content" and "type" keys)
            full_document: Full document text for context
            show_progress: Whether to show progress logs

        Returns:
            List of chunks with contextualized_content field added

        Raises:
            ContextualizationError: If batch processing fails
        """
        if not chunks:
            raise ContextualizationError("No chunks provided for contextualization")

        # Count tables
        table_count = sum(1 for c in chunks if c.get("type") == "table")

        logger.info(f"Contextualizing {table_count} tables out of {len(chunks)} total chunks")

        contextualized_chunks = []
        processed_tables = 0
        failed_tables = 0

        for i, chunk in enumerate(chunks, 1):
            chunk_type = chunk.get("type", "text")
            content = chunk.get("content", "")

            # Only contextualize tables
            if chunk_type == "table":
                try:
                    if show_progress:
                        logger.info(
                            f"Contextualizing table {processed_tables + 1}/{table_count}..."
                        )

                    contextualized = await self.contextualize_table(content, full_document)

                    chunk["contextualized_content"] = contextualized
                    processed_tables += 1

                except Exception as e:
                    logger.error(f"Failed to contextualize chunk {i}: {e}")
                    chunk["contextualized_content"] = content  # Fallback to original
                    failed_tables += 1
            else:
                # Text/headers: use original content
                chunk["contextualized_content"] = content

            contextualized_chunks.append(chunk)

        # Summary
        if table_count > 0:
            success_rate = (processed_tables / table_count) * 100
            logger.success(
                f"Contextualization complete: {processed_tables}/{table_count} tables succeeded "
                f"({success_rate:.1f}%)"
            )

            if failed_tables > 0:
                logger.warning(f"{failed_tables} tables failed (using original content)")

        return contextualized_chunks

    def close(self):
        """
        Close the API client connection.

        Should be called when done processing to clean up resources.
        """
        try:
            # AsyncOpenAI doesn't require explicit closing in most cases
            # but we log it for clarity
            logger.debug("Closing contextualizer client")
        except Exception as e:
            logger.warning(f"Error closing client: {e}")


class NoOpContextualizer:
    """
    No-op contextualizer that passes through content unchanged.

    Used when contextualization is disabled to maintain consistent interface.
    """

    def __init__(self):
        logger.info("Using no-op contextualizer (no LLM calls)")

    async def contextualize_table(self, table_text: str, full_document: str, **kwargs) -> str:
        """Return original content unchanged."""
        return table_text

    async def contextualize_batch(self, chunks: list, full_document: str, **kwargs) -> list:
        """Return chunks with original content."""
        for chunk in chunks:
            chunk["contextualized_content"] = chunk.get("content", "")
        return chunks

    def close(self):
        """No resources to close."""
        pass
