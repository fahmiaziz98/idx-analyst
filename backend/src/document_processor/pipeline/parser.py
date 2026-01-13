import io
from pathlib import Path

import fitz
from loguru import logger
from PIL import Image

from src.core.exception import ParsingError, ValidationError
from src.document_processor.pipeline.prompt import (
    PARSER_SYSTEM_PROMPT,
    PARSER_USER_PROMPT,
)
from src.rag.llm_client import VLMClient


class DocumentParser:
    """
    PDF parser using VLM for document-to-markdown conversion.

    This class provides:
    - PDF validation and page count retrieval
    - Page range extraction as PIL Images
    - Async document parsing to markdown using VLM

    Attributes:
        parser: VLMClient instance for VLM inference.

    Example:
        >>> parser = DocumentParser()
        >>> markdown_pages = await parser.parse_pdf("report.pdf", start_page=1, end_page=5)
    """

    def __init__(
        self,
        temperature: float = 1.5,
        min_p: float = 0.1,
        max_tokens: int = 8192,
    ) -> None:
        """
        Initialize the document parser with VLM configuration.

        Args:
            temperature: Sampling temperature for VLM generation. Higher values
                produce more creative output. Defaults to 1.5.
            min_p: Minimum probability threshold for nucleus sampling.
                Defaults to 0.1.
            max_tokens: Maximum tokens for VLM response. Defaults to 8192.

        Raises:
            ParsingError: If VLMClient initialization fails.
        """
        try:
            logger.info("Initializing VLMClient...")
            self.parser = VLMClient(
                max_tokens=max_tokens,
                min_p=min_p,
                temperature=temperature,
            )
            logger.success("VLMClient initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize VLMClient: {e}")
            raise ParsingError(f"Failed to initialize VLMClient: {e}") from e

    @staticmethod
    def _extract_markdown(text: str) -> str:
        """
        Extract markdown content from code block wrappers.

        VLMs often wrap output in ```markdown ... ``` blocks.
        This method strips those wrappers to get clean markdown.

        Args:
            text: Raw text that may contain markdown code block wrappers.

        Returns:
            Clean markdown text without code block wrappers.

        Example:
            >>> DocumentParser._extract_markdown("```markdown\\n# Title\\n```")
            '# Title'
        """
        text = text.strip()

        # Check for ```markdown or ```md at the start
        if text.startswith("```markdown"):
            text = text[len("```markdown") :]
        elif text.startswith("```md"):
            text = text[len("```md") :]
        elif text.startswith("```"):
            text = text[3:]

        # Remove trailing ```
        if text.endswith("```"):
            text = text[:-3]

        return text.strip()

    def validate_pdf(self, pdf_path: str) -> Path:
        """
        Validate that a PDF file exists and is readable.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Validated Path object for the PDF file.

        Raises:
            ValidationError: If file doesn't exist, is not a PDF,
                or is corrupted/unreadable.
        """
        path = Path(pdf_path)

        if not path.exists():
            raise ValidationError(f"File does not exist: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ValidationError(f"File is not a PDF: {pdf_path}")

        try:
            with fitz.open(str(path)) as doc:
                page_count = len(doc)
                logger.debug(f"PDF validated: {path.name} ({page_count} pages)")
        except Exception as e:
            raise ValidationError(f"Invalid or corrupted PDF: {e}") from e

        return path

    def get_page_count(self, pdf_path: str) -> int:
        """
        Get the total number of pages in a PDF file.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Number of pages in the PDF.

        Raises:
            ValidationError: If file is invalid or unreadable.
        """
        pdf_path_obj = self.validate_pdf(pdf_path)

        try:
            with fitz.open(str(pdf_path_obj)) as doc:
                return len(doc)
        except Exception as e:
            raise ValidationError(f"Failed to get page count: {e}") from e

    def extract_pages_as_images(
        self,
        pdf_path: str,
        start_page: int = 1,
        end_page: int | None = None,
        scale: float = 4.0,
    ) -> list[Image.Image]:
        """
        Extract PDF pages as high-resolution PIL Images.

        Converts each page to a PNG image at the specified scale factor.
        Useful for VLM processing where image quality affects accuracy.

        Args:
            pdf_path: Path to the PDF file.
            start_page: First page to extract (1-indexed, inclusive). Defaults to 1.
            end_page: Last page to extract (1-indexed, inclusive).
                Defaults to None (last page of document).
            scale: Resolution scale factor. 4.0 = 4x native resolution.
                Higher values produce clearer images but use more memory.
                Defaults to 4.0.

        Returns:
            List of PIL Image objects, one per extracted page.

        Raises:
            ValidationError: If page range is invalid.
            ParsingError: If image extraction fails.

        Example:
            >>> images = parser.extract_pages_as_images("report.pdf", 1, 5)
            >>> len(images)
            5
        """
        pdf_path_obj = self.validate_pdf(pdf_path)
        images: list[Image.Image] = []

        try:
            with fitz.open(str(pdf_path_obj)) as pdf_document:
                total_pages = len(pdf_document)

                # Default end_page to last page
                actual_end_page = end_page if end_page is not None else total_pages

                # Validate page range
                if start_page < 1:
                    raise ValidationError(f"start_page must be >= 1 (got {start_page})")

                if actual_end_page < start_page:
                    raise ValidationError(
                        f"end_page ({actual_end_page}) must be >= start_page ({start_page})"
                    )

                if actual_end_page > total_pages:
                    raise ValidationError(
                        f"end_page ({actual_end_page}) exceeds total pages ({total_pages})"
                    )

                logger.info(
                    f"Extracting pages {start_page}-{actual_end_page} from {pdf_path_obj.name}"
                )

                # Extract pages (convert to 0-indexed for PyMuPDF)
                matrix = fitz.Matrix(scale, scale)
                for page_num in range(start_page - 1, actual_end_page):
                    page = pdf_document[page_num]
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)

                    img_data = pixmap.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    images.append(img)

                logger.success(f"Extracted {len(images)} page(s) as images")
                return images

        except ValidationError:
            raise
        except Exception as e:
            raise ParsingError(f"Failed to extract pages: {e}") from e

    async def parse_pdf(
        self,
        pdf_path: str,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> list[str]:
        """
        Parse PDF pages to markdown using VLM.

        Extracts specified pages as images and sends each to the VLM
        for conversion to markdown format.

        Args:
            pdf_path: Path to the PDF file.
            start_page: First page to parse (1-indexed). Defaults to 1.
            end_page: Last page to parse (1-indexed).
                Defaults to None (last page of document).

        Returns:
            List of markdown strings, one per page.

        Raises:
            ValidationError: If inputs are invalid.
            ParsingError: If VLM parsing fails.

        Example:
            >>> markdown_pages = await parser.parse_pdf("report.pdf", 1, 3)
            >>> print(markdown_pages[0])  # First page as markdown
        """
        # Validate and get page count
        self.validate_pdf(pdf_path)
        total_pages = self.get_page_count(pdf_path)
        actual_end_page = end_page if end_page is not None else total_pages

        logger.info(f"Parsing {Path(pdf_path).name} (pages {start_page}-{actual_end_page})")

        # Extract pages as images
        images = self.extract_pages_as_images(
            pdf_path,
            start_page=start_page,
            end_page=actual_end_page,
        )

        # Parse each page with VLM
        markdown_pages: list[str] = []
        for idx, img in enumerate(images, start=start_page):
            try:
                logger.info(f"Parsing page {idx}...")
                markdown = await self.parser.generate_with_image(
                    image=img,
                    system_prompt=PARSER_SYSTEM_PROMPT,
                    user_prompt=PARSER_USER_PROMPT,
                )
                clean_markdown = self._extract_markdown(markdown)
                markdown_pages.append(clean_markdown)
                logger.info(f"Page {idx} parsed successfully")

            except Exception as e:
                raise ParsingError(f"VLM parsing failed on page {idx}: {e}") from e

        logger.success(f"Parsed {len(markdown_pages)} page(s) successfully")
        return markdown_pages
