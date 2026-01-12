import hashlib
import re
from uuid import NAMESPACE_DNS, uuid5

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from src.core.exception import ChunkingError
from src.schemas.processor import DocumentElement


class DocumentChunker:
    """
    Document chunker with markdown parsing and intelligent splitting.

    This class handles:
    - Parsing markdown into structured elements (headers, paragraphs, tables)
    - Table detection using pipe (|) character
    - Token-based chunking with RecursiveCharacterTextSplitter
    - Header validation and reclassification
    - UUID generation for chunks

    Attributes:
        chunk_size: Maximum tokens per chunk
        chunk_overlap: Overlap tokens between chunks
        header_max_tokens: Max tokens for headers (convert to paragraph if exceeded)
        min_tokens: Minimum tokens to keep a chunk
        tokenizer: tiktoken encoder for token counting
        text_splitter: LangChain text splitter
    """

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 150,
        header_max_tokens: int = 64,
        min_tokens: int = 64,
    ):
        """
        Initialize the document chunker.

        Args:
            chunk_size: Maximum tokens per chunk (default: 1024)
            chunk_overlap: Overlap tokens between chunks (default: 150)
            header_max_tokens: Max tokens for headers (default: 64)
            min_tokens: Minimum tokens to keep a chunk (default: 64)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.header_max_tokens = header_max_tokens
        self.min_tokens = min_tokens

        self.tokenizer = tiktoken.get_encoding("cl100k_base")

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        logger.debug(
            f"Chunker initialized: chunk_size={chunk_size}, "
            f"overlap={chunk_overlap}, min_tokens={min_tokens}"
        )

    def parse_markdown(self, markdown_text: str) -> list[DocumentElement]:
        """
        Parse markdown text into structured elements.

        Detects:
        - Headers: Lines starting with # (1-4 levels)
        - Tables: Lines containing pipes (|) with at least 3 pipes
        - Paragraphs: Everything else

        Args:
            markdown_text: Raw markdown text

        Returns:
            List of DocumentElement objects

        Raises:
            ChunkingError: If parsing fails
        """
        if not markdown_text or not markdown_text.strip():
            raise ChunkingError("Empty markdown text provided")

        try:
            elements = []
            lines = markdown_text.split("\n")

            current_buffer = []
            current_type = None
            in_table = False

            logger.debug(f"Parsing markdown ({len(lines)} lines)")

            for line in lines:
                if not line.strip():
                    if current_buffer and not in_table:
                        elements.append(
                            DocumentElement(
                                element_type=current_type, content="\n".join(current_buffer)
                            )
                        )
                        current_buffer = []
                        current_type = None
                    continue

                if "|" in line and line.count("|") >= 3:
                    if not in_table:
                        if current_buffer:
                            elements.append(
                                DocumentElement(
                                    element_type=current_type, content="\n".join(current_buffer)
                                )
                            )
                        current_buffer = [line]
                        current_type = "table"
                        in_table = True
                    else:
                        current_buffer.append(line)
                    continue

                if in_table:
                    elements.append(
                        DocumentElement(element_type="table", content="\n".join(current_buffer))
                    )
                    current_buffer = []
                    current_type = None
                    in_table = False

                line_type = self._detect_line_type(line)

                if current_type in (None, line_type):
                    current_buffer.append(line)
                    current_type = line_type
                else:
                    elements.append(
                        DocumentElement(
                            element_type=current_type, content="\n".join(current_buffer)
                        )
                    )
                    current_buffer = [line]
                    current_type = line_type

            if current_buffer:
                elements.append(
                    DocumentElement(
                        element_type=current_type or "paragraph", content="\n".join(current_buffer)
                    )
                )

            type_counts = {}
            for elem in elements:
                type_counts[elem.element_type] = type_counts.get(elem.element_type, 0) + 1

            logger.info(f"Parsed {len(elements)} elements: {type_counts}")
            return elements

        except Exception as e:
            raise ChunkingError(f"Failed to parse markdown: {str(e)}") from e

    def _detect_line_type(self, line: str) -> str:
        """
        Detect the type of a markdown line.

        Args:
            line: Single line of text

        Returns:
            Element type: "header" or "paragraph"
        """
        # Markdown headers (# to ####)
        if re.match(r"^#{1,4}\s+", line):
            return "header"
        return "paragraph"

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        try:
            return len(self.tokenizer.encode(text))
        except Exception as e:
            logger.warning(f"Token counting failed: {e}, using character-based estimate")
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(text) // 4

    def chunk_elements(self, elements: list[DocumentElement]) -> list[dict]:
        """
        Chunk document elements into processable chunks.

        Strategy:
        - Tables: Always kept as single chunks (never split)
        - Headers: Validated against max token limit
        - Text/Paragraphs: Split using RecursiveCharacterTextSplitter

        Args:
            elements: List of parsed DocumentElement objects

        Returns:
            List of chunk dictionaries with "content" and "type" keys

        Raises:
            ChunkingError: If chunking fails
        """
        if not elements:
            raise ChunkingError("No elements provided for chunking")

        try:
            chunks = []
            text_buffer = []

            logger.info(f"Chunking {len(elements)} elements")

            for element in elements:
                token_count = self.count_tokens(element.content)

                # Validate headers (convert to paragraph if too long)
                if element.element_type == "header":
                    if token_count > self.header_max_tokens:
                        logger.debug(
                            f"Header exceeds {self.header_max_tokens} tokens "
                            f"({token_count}), converting to paragraph"
                        )
                        element.element_type = "paragraph"

                # Handle tables (always standalone)
                if element.element_type == "table":
                    # Flush text buffer first
                    if text_buffer:
                        text_chunks = self._split_text_elements(text_buffer)
                        chunks.extend(text_chunks)
                        text_buffer = []

                    # Add table as single chunk
                    chunks.append({"content": element.content, "type": "table"})
                    logger.debug(f"Added table chunk ({token_count} tokens)")
                    continue

                # Accumulate text/headers for batch splitting
                text_buffer.append(element)

            # Flush remaining text buffer
            if text_buffer:
                text_chunks = self._split_text_elements(text_buffer)
                chunks.extend(text_chunks)

            # Log statistics
            table_count = sum(1 for c in chunks if c["type"] == "table")
            text_count = len(chunks) - table_count

            logger.success(
                f"Generated {len(chunks)} chunks ({table_count} tables, {text_count} text)"
            )

            return chunks

        except Exception as e:
            raise ChunkingError(f"Failed to chunk elements: {str(e)}") from e

    def _split_text_elements(self, elements: list[DocumentElement]) -> list[dict]:
        """
        Split text elements using RecursiveCharacterTextSplitter.

        Combines all text elements into one string, splits it,
        then filters by minimum token count.

        Args:
            elements: List of text/header DocumentElement objects

        Returns:
            List of text chunk dictionaries
        """
        combined_text = "\n\n".join(e.content for e in elements)

        text_chunks = self.text_splitter.split_text(combined_text)

        valid_chunks = []
        skipped = 0

        for chunk_text in text_chunks:
            token_count = self.count_tokens(chunk_text)

            if token_count >= self.min_tokens:
                valid_chunks.append({"content": chunk_text, "type": "text"})
            else:
                skipped += 1
                logger.debug(f"Skipped chunk with {token_count} tokens (min: {self.min_tokens})")

        if skipped > 0:
            logger.debug(f"Skipped {skipped} chunks below minimum token threshold")

        return valid_chunks

    def generate_chunk_id(self, content: str) -> str:
        """
        Generate deterministic UUID for chunk based on content hash.

        Uses MD5 hash of content as seed for UUID5 generation.
        This ensures same content always gets same ID.

        Args:
            content: Chunk text content

        Returns:
            UUID string
        """
        # Generate MD5 hash of content
        content_hash = hashlib.md5(content.encode()).hexdigest()

        # Generate UUID5 using DNS namespace
        chunk_uuid = uuid5(NAMESPACE_DNS, content_hash)

        return str(chunk_uuid)
