from dataclasses import dataclass, asdict
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


@dataclass
class DocumentElement:
    """
    Represents a parsed element from markdown document.
    
    Attributes:
        element_type: Type of element (header, paragraph, table)
        content: Raw text content of the element
    """
    element_type: Literal["header", "paragraph", "table"]
    content: str

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return asdict(self)


@dataclass
class ChunkMetadata:
    """
    Metadata for a document chunk.
    
    Attributes:
        company_name: Name of the company
        tickers: Stock ticker symbol(s)
        year: Reporting year
        page_number: Page number in original document
        document_path: Path to original document file
    """
    company_name: str
    tickers: str
    year: int
    page_number: int
    document_path: str
    element_type: Literal["header", "paragraph", "table", "text"]

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return asdict(self)


@dataclass
class Chunk:
    """
    Represents a processed document chunk.
    
    Attributes:
        id: Unique identifier (UUID based on content hash)
        chunk_text: The chunked text content
        text: Original full document text
        metadata: Chunk metadata (company, ticker, page, etc.)
        contextual_text: Contextualized version of chunk (from LLM)
    """
    id: str
    chunk_text: str
    text: str
    metadata: Dict
    contextual_text: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return asdict(self)


@dataclass
class ProcessingStats:
    """
    Statistics for document processing.
    
    Attributes:
        total_chunks: Total number of chunks generated
        table_chunks: Number of table chunks
        text_chunks: Number of text chunks
        contextualized_chunks: Number of chunks with LLM context
        skipped_chunks: Number of chunks skipped (e.g., too small)
        processing_time: Total processing time in seconds
    """
    total_chunks: int = 0
    table_chunks: int = 0
    text_chunks: int = 0
    contextualized_chunks: int = 0
    skipped_chunks: int = 0
    processing_time: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return asdict(self)


@dataclass
class ProcessingResult:
    """
    Result of document processing pipeline.
    
    Attributes:
        status: Processing status (COMPLETED, FAILED, PARTIAL)
        output_path: Path to saved output file
        stats: Processing statistics
        error: Error message if failed
    """
    status: Literal["COMPLETED", "FAILED", "PARTIAL"]
    output_path: Optional[str] = None
    stats: Optional[ProcessingStats] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        result = {
            "status": self.status,
            "output_path": self.output_path,
            "error": self.error
        }
        if self.stats:
            result["stats"] = self.stats.to_dict()
        return result
