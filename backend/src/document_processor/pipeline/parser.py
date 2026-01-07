from pathlib import Path

import fitz
from llama_cloud_services import LlamaParse
from loguru import logger

from src.core.exception import ParsingError, ValidationError


class DocumentParser:
    """
    PDF parser using LlamaParse with support for page extraction.

    This class handles:
    - PDF validation
    - Page range extraction (creates temporary files)
    - Document parsing to markdown format
    - Cleanup of temporary files

    Attributes:
        parser: LlamaParse instance
        api_key: LlamaParse API key
    """

    def __init__(self, api_key: str):
        """
        Initialize the document parser.

        Args:
            api_key: LlamaParse API key

        Raises:
            ValidationError: If API key is invalid
        """
        if not api_key:
            raise ValidationError("API key is required")
        try:
            logger.info("Initializing LlamaParse...")
            self.parser = LlamaParse(
                api_key=api_key,
                num_workers=4,
                model="openai-gpt-4o-mini",
                invalidate_cache=False,
                parse_mode="parse_page_with_agent",
                language="en",
                adaptive_long_table=True,
                outlined_table_extraction=True,
                high_res_ocr=True,
                precise_bounding_box=True,
                hide_footers=True,
                system_prompt_append="""
                    Parse the PDF financial report carefully.
                    Focus on extracting tables with financial data (e.g., balance sheets, income statements) in markdown format.
                    Preserve structures like columns for notes and years, currencies (Rp, USD), and units (million, billion, and trillion). 
                    Handle mixed English-Indonesian text: Translate key Indonesian terms to English if ambiguous (e.g., 'total aset' to 'total assets').
                    Ignore irrelevant sections like disclaimers unless they contain tables.
                """,
            )
            logger.success("LlamaParse initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize LlamaParse: {str(e)}")
            raise ParsingError(f"Failed to initialize LlamaParse: {str(e)}") from e

    def validate_pdf(self, pdf_path: str) -> Path:
        """
        Validate PDF file exists and is readable.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Path object for the PDF file

        Raises:
            ValidationError: If file doesn't exist or is not a PDF
        """
        path = Path(pdf_path)

        if not path.exists():
            raise ValidationError(f"File does not exist: {pdf_path}")
        if path.suffix != ".pdf":
            raise ValidationError(f"File is not a PDF: {pdf_path}")

        try:
            with fitz.open(str(path)) as doc:
                page_count = len(doc)
                logger.debug(f"PDF validated: {path.name} ({page_count} pages)")
        except Exception as e:
            raise ValidationError(f"Invalid or corrupted PDF: {str(e)}") from e

        return path

    def extract_page_range(self, pdf_path: str, start_page: int, end_page: int) -> tuple[str, str]:
        """
        Extract a specific page range from PDF.

        Creates a temporary PDF file with only the specified pages.
        Caller is responsible for cleaning up the temporary file.

        Args:
            pdf_path: Path to original PDF file
            start_page: Starting page number (1-indexed, inclusive)
            end_page: Ending page number (1-indexed, inclusive)

        Returns:
            Tuple of (temp_file_path, original_file_path)

        Raises:
            ValidationError: If page range is invalid
            ParsingError: If extraction fails
        """
        pdf_path_obj = self.validate_pdf(pdf_path)

        try:
            with fitz.open(str(pdf_path_obj)) as doc:
                total_pages = len(doc)

                # Validate page range
                if start_page < 1 or end_page < 1:
                    raise ValidationError(
                        f"Page numbers must be >= 1 (got {start_page}-{end_page})"
                    )

                if start_page > end_page:
                    raise ValidationError(
                        f"start_page ({start_page}) must be <= end_page ({end_page})"
                    )

                if end_page > total_pages:
                    raise ValidationError(
                        f"end_page ({end_page}) exceeds total pages ({total_pages})"
                    )

                # Create temporary file
                temp_filename = f"temp_{pdf_path_obj.stem}_{start_page}_{end_page}.pdf"
                temp_path = Path.cwd() / temp_filename

                logger.info(f"Extracting pages {start_page}-{end_page} from {pdf_path_obj.name}")

                # Extract pages (convert to 0-indexed)
                new_doc = fitz.open()
                for page_num in range(start_page - 1, end_page):
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

                new_doc.save(str(temp_path))
                new_doc.close()

                logger.success(f"Created temporary file: {temp_path.name}")
                return str(temp_path), str(pdf_path_obj)

        except ValidationError:
            raise
        except Exception as e:
            raise ParsingError(f"Failed to extract page range: {str(e)}") from e

    async def parse_pdf(
        self, pdf_path: str, start_page: int | None = None, end_page: int | None = None
    ) -> tuple[list, str]:
        """
        Parse PDF to markdown documents.

        If page range is specified, creates a temporary file first.
        Returns markdown documents split by page.

        Args:
            pdf_path: Path to PDF file
            start_page: Optional starting page (1-indexed)
            end_page: Optional ending page (1-indexed)

        Returns:
            Tuple of (markdown_documents, original_file_path)
            Each markdown document has .text and .metadata attributes

        Raises:
            ParsingError: If parsing fails
            ValidationError: If inputs are invalid
        """
        # Validate input
        original_path = self.validate_pdf(pdf_path)
        temp_file = None

        try:
            # Extract page range if specified
            if start_page is not None and end_page is not None:
                temp_file, original_file = self.extract_page_range(pdf_path, start_page, end_page)
                file_to_parse = temp_file
            else:
                file_to_parse = str(original_path)
                original_file = str(original_path)

            # Parse with LlamaParse
            logger.info(f"Parsing document: {Path(file_to_parse).name}")

            try:
                result = await self.parser.aparse(file_to_parse)
                markdown_docs = result.get_markdown_documents(split_by_page=True)

                logger.success(f"Parsed {len(markdown_docs)} pages successfully")
                return markdown_docs, original_file

            except Exception as e:
                raise ParsingError(f"LlamaParse failed: {str(e)}") from e

        finally:
            # Clean up temporary file
            if temp_file and Path(temp_file).exists():
                try:
                    Path(temp_file).unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")

    def get_page_count(self, pdf_path: str) -> int:
        """
        Get the number of pages in a PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Number of pages in the PDF file

        Raises:
            ValidationError: If file doesn't exist or is not a PDF
        """
        pdf_path_obj = self.validate_pdf(pdf_path)

        try:
            with fitz.open(str(pdf_path_obj)) as doc:
                return len(doc)
        except Exception as e:
            raise ValidationError(f"Failed to get page count: {str(e)}") from e
