import json
import time
from pathlib import Path

from loguru import logger

from src.core.exception import (
    ChunkingError,
    ContextualizationError,
    DocumentProcessorError,
    ParsingError,
)
from src.document_processor.pipeline import (
    DocumentChunker,
    DocumentParser,
    NoOpContextualizer,
    TableContextualizer,
)
from src.schemas.processor import ChunkMetadata, ProcessingResult, ProcessingStats

DEFAULT_OUTPUT_FILENAME = "processed_data.json"


class DocumentProcessor:
    """
    Main document processing orchestrator.

    This class coordinates the entire pipeline:
    - Parsing PDFs to markdown
    - Chunking documents with table detection
    - Contextualizing tables with LLM
    - Managing output with ID tracking and append mode

    Attributes:
        parser: DocumentParser instance
        chunker: DocumentChunker instance
        contextualizer: TableContextualizer or NoOpContextualizer
        stats: ProcessingStats for current operation
    """

    def __init__(
        self,
        enable_contextualization: bool = True,
        chunk_size: int = 1024,
        chunk_overlap: int = 150,
        temperature: float = 1.5,
        max_tokens: int = 8192,
        **kwargs,
    ):
        """
        Initialize the document processor.

        Args:
            enable_contextualization: Whether to use LLM for table context
            chunk_size: Maximum tokens per chunk
            chunk_overlap: Overlap tokens between chunks
            temperature: LLM temperature for parsing/contextualization
            max_tokens: Max tokens for LLM generation
            **kwargs: Additional config (model_name, base_url, etc.)

        Raises:
            DocumentProcessorError: If initialization fails
        """
        logger.info("Initializing DocumentProcessor")

        try:
            self.parser = DocumentParser(temperature=temperature, max_tokens=max_tokens)

            self.chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

            if enable_contextualization:
                self.contextualizer = TableContextualizer(
                    temperature=kwargs.get("context_temperature", 1.0),
                    max_tokens=kwargs.get("context_max_tokens", 4096),
                )
                logger.info("Contextualization enabled")
            else:
                self.contextualizer = NoOpContextualizer()
                logger.info("Contextualization disabled")

            self.stats = ProcessingStats()

            logger.success("DocumentProcessor initialized successfully")

        except Exception as e:
            raise DocumentProcessorError(f"Failed to initialize processor: {str(e)}") from e

    async def process_document(
        self,
        input_file: str,
        company_name: str,
        ticker: str,
        year: int,
        output_dir: str = "data/processed",
        output_filename: str = DEFAULT_OUTPUT_FILENAME,
        start_page: int = 1,
        end_page: int | None = None,
        mode: str = "append",
    ) -> ProcessingResult:
        """
        Process a single document through the complete pipeline.

        Pipeline steps:
        1. Parse PDF pages to markdown using VLM
        2. Split markdown into chunks with table detection
        3. Contextualize tables with LLM (Qwen3-VL)
        4. Generate IDs and attach metadata
        5. Save to JSON (append or new mode)

        Args:
            input_file: Path to input PDF
            company_name: Company name for metadata
            ticker: Stock ticker symbol
            year: Reporting year
            output_dir: Output directory path
            output_filename: Output JSON filename
            start_page: Starting page (1-indexed, default: 1)
            end_page: Optional ending page (1-indexed)
            mode: "append" or "new"

        Returns:
            ProcessingResult with status, stats, and output path
        """
        start_time = time.time()
        self.stats = ProcessingStats()  # Reset stats

        logger.info("=" * 80)
        logger.info(f"Processing: {Path(input_file).name}")
        logger.info(f"Company: {company_name} ({ticker})")
        logger.info(f"Year: {year}")
        logger.info(f"Mode: {mode.upper()}")
        if end_page:
            logger.info(f"Pages: {start_page}-{end_page}")
        else:
            logger.info(f"Pages: {start_page}-EOF")
        logger.info("=" * 80)

        try:
            # Step 1: Parse PDF
            logger.info("Step 1/5: Parsing PDF to markdown via VLM")
            markdown_docs = await self.parser.parse_pdf(input_file, start_page, end_page)

            # Step 2: Process each page
            logger.info(f"Step 2/5: Processing {len(markdown_docs)} parsed pages")
            all_chunks = []

            for page_idx, markdown_text in enumerate(markdown_docs, start=0):
                # Calculate actual page number
                actual_page = start_page + page_idx

                logger.debug(f"  Processing page {actual_page}...")

                # Parse markdown to elements
                elements = self.chunker.parse_markdown(markdown_text)

                # Chunk elements
                chunks = self.chunker.chunk_elements(elements)

                # Add page-specific info and full text for context
                for chunk in chunks:
                    chunk["page"] = actual_page
                    chunk["full_page_text"] = markdown_text

                all_chunks.extend(chunks)

            logger.success(f"Generated {len(all_chunks)} chunks from {len(markdown_docs)} pages")

            # Step 3: Contextualize tables
            logger.info("Step 3/5: Contextualizing tables")

            # Process in batch for the whole document/range
            # Note: contextualize_batch handles filtering for 'table' type
            contextualized_chunks = []

            # Since chunks already have 'full_page_text', we can process page by page
            # or try to group if contextualizer supports it.
            # Current contextualizer takes full_document.
            # We'll process page by page to keep it consistent with the table context.

            for page_idx in range(len(markdown_docs)):
                curr_page_num = start_page + page_idx
                page_markdown = markdown_docs[page_idx]
                page_chunks = [c for c in all_chunks if c.get("page") == curr_page_num]

                if page_chunks:
                    page_contextualized = await self.contextualizer.contextualize_batch(
                        page_chunks, page_markdown, show_progress=False
                    )
                    contextualized_chunks.extend(page_contextualized)

            # Step 4: Build final chunks with metadata
            logger.info("Step 4/5: Building chunks with metadata")
            final_chunks = self._build_final_chunks(
                contextualized_chunks, company_name, ticker, year, input_file
            )

            # Update stats
            self.stats.total_chunks = len(final_chunks)
            self.stats.table_chunks = sum(1 for c in all_chunks if c.get("type") == "table")
            self.stats.text_chunks = self.stats.total_chunks - self.stats.table_chunks
            self.stats.contextualized_chunks = sum(
                1 for c in final_chunks if c.get("contextual_text") != c.get("chunk_text")
            )

            # Step 5: Save output
            logger.info("Step 5/5: Saving output")
            output_path = self._save_chunks(final_chunks, output_dir, output_filename, mode)

            # Calculate processing time
            self.stats.processing_time = time.time() - start_time

            logger.success("=" * 80)
            logger.success(f"Processing completed in {self.stats.processing_time:.2f}s")
            logger.success(f"Output: {output_path}")
            logger.success(f"Stats: {self.stats.to_dict()}")
            logger.success("=" * 80)

            return ProcessingResult(
                status="COMPLETED", output_path=str(output_path), stats=self.stats
            )

        except (ParsingError, ChunkingError, ContextualizationError) as e:
            logger.error(f"Processing failed: {e}")
            self.stats.processing_time = time.time() - start_time

            return ProcessingResult(status="FAILED", stats=self.stats, error=str(e))

        except Exception as e:
            logger.exception(f"Unexpected error during processing: {e}")
            self.stats.processing_time = time.time() - start_time

            return ProcessingResult(
                status="FAILED", stats=self.stats, error=f"Unexpected error: {str(e)}"
            )

    def _build_final_chunks(
        self, chunks: list[dict], company_name: str, ticker: str, year: int, document_path: str
    ) -> list[dict]:
        """
        Build final chunk objects with IDs and metadata.

        Args:
            chunks: List of processed chunks
            company_name: Company name
            ticker: Stock ticker
            year: Reporting year
            document_path: Path to original document

        Returns:
            List of final chunk dictionaries
        """
        final_chunks = []

        for chunk_data in chunks:
            # Generate UUID for chunk
            chunk_id = self.chunker.generate_chunk_id(chunk_data["content"])

            # Build metadata
            metadata = ChunkMetadata(
                company_name=company_name,
                tickers=ticker,
                year=year,
                page_number=chunk_data.get("page", 0),
                document_path=Path(document_path).name,  # Use original filename only
            ).to_dict()

            # Build chunk object (matching old schema)
            chunk = {
                "id": chunk_id,
                "contextual_text": chunk_data.get("contextualized_content", chunk_data["content"]),
                "chunk_text": chunk_data["content"],
                "text": chunk_data.get("full_page_text", ""),
                "metadata": metadata,
            }

            final_chunks.append(chunk)

        logger.info(f"Built {len(final_chunks)} final chunks")
        return final_chunks

    def _save_chunks(
        self, chunks: list[dict], output_dir: str, output_filename: str, mode: str
    ) -> Path:
        """
        Save chunks to JSON file with append mode support.

        In append mode, loads existing file and adds new chunks.
        In new mode, overwrites existing file.

        Args:
            chunks: List of chunk dictionaries to save
            output_dir: Output directory path
            output_filename: Output JSON filename
            mode: "append" or "new"

        Returns:
            Path to saved file

        Raises:
            OutputError: If saving fails
        """
        try:
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            output_file = output_path / output_filename

            # Load existing data in append mode
            if mode == "append" and output_file.exists():
                logger.info(f"Loading existing data from {output_file}")

                try:
                    with open(output_file, encoding="utf-8") as f:
                        existing_data = json.load(f)

                    # Get ticker for logging
                    new_ticker = chunks[0]["metadata"]["tickers"] if chunks else "unknown"

                    logger.info(f"Found {len(existing_data)} existing chunks")

                    # Combine data
                    combined_data = existing_data + chunks

                    logger.info(f"Adding {len(chunks)} new chunks for {new_ticker}")

                except json.JSONDecodeError as e:
                    raise DocumentProcessorError(f"Failed to parse existing JSON: {e}") from e
            else:
                if mode == "new":
                    logger.info("Starting fresh (NEW mode)")
                combined_data = chunks

            # Save combined data
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(combined_data, f, indent=4, ensure_ascii=False)

            logger.success(
                f"Saved {len(chunks)} new chunks "
                f"(Total: {len(combined_data)} chunks in {output_filename})"
            )

            return output_file

        except Exception as e:
            raise DocumentProcessorError(f"Failed to save output: {str(e)}") from e

    async def close(self):
        """
        Close all resources and connections.

        Should be called when done processing to clean up.
        """
        logger.info("Closing document processor")

        try:
            await self.contextualizer.close()
        except Exception as e:
            logger.warning(f"Error closing contextualizer: {e}")
