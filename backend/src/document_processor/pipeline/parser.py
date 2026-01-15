from pathlib import Path

import fitz
import numpy as np
from loguru import logger
from pdf2image import convert_from_path
from PIL import Image

from src.core.exception import ParsingError, ValidationError
from src.document_processor.pipeline.crop import ContentCroper
from src.document_processor.pipeline.prompt import (
    PARSER_SYSTEM_PROMPT,
    PARSER_USER_PROMPT,
)
from src.rag.llm_client import VLMClient
from src.utils.timing import Timer


class DocumentParser:
    """
    PDF parser using VLM for document-to-markdown conversion.

    This class provides:
    - PDF validation and page count retrieval
    - High-quality page rasterization using pdf2image
    - Intelligent whitespace cropping
    - Async document parsing to markdown using VLM

    Attributes:
        parser: VLMClient instance for VLM inference.
        dpi: Dots Per Inch for rasterization (default: 300).
        cropper: ContentCroper instance for image post-processing.
    """

    def __init__(
        self,
        temperature: float = 1.5,
        min_p: float = 0.1,
        max_tokens: int = 8192,
        dpi: int = 300,
        enable_cropping: bool = True,
    ) -> None:
        """
        Initialize the document parser with VLM and processing configuration.

        Args:
            temperature: Sampling temperature for VLM generation.
            min_p: Minimum probability threshold for nucleus sampling.
            max_tokens: Maximum tokens for VLM response.
            dpi: DPI for PDF rasterization. Higher means better quality but slower.
                Defaults to 300.
            enable_cropping: Whether to apply intelligent whitespace cropping.
                Defaults to True.
        """
        self.dpi = dpi
        self.enable_cropping = enable_cropping
        self.cropper = ContentCroper() if enable_cropping else None

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

        Args:
            text: Raw text that may contain markdown code block wrappers.

        Returns:
            Clean markdown text without code block wrappers.
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
        """
        path = Path(pdf_path)

        if not path.exists():
            raise ValidationError(f"File does not exist: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ValidationError(f"File is not a PDF: {pdf_path}")

        try:
            # We still use fitz for quick validation as it's faster than pdf2image
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
        """
        pdf_path_obj = self.validate_pdf(pdf_path)

        try:
            # pdf2image uses poppler's pdfinfo, but fitz is lightweight and we have it
            with fitz.open(str(pdf_path_obj)) as doc:
                return len(doc)
        except Exception as e:
            raise ValidationError(f"Failed to get page count: {e}") from e

    def extract_pages_as_images(
        self,
        pdf_path: str,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> list[Image.Image]:
        """
        Extract PDF pages as high-resolution PIL Images using pdf2image.

        Applies intelligent cropping if enabled.

        Args:
            pdf_path: Path to the PDF file.
            start_page: First page to extract (1-indexed, inclusive).
            end_page: Last page to extract (1-indexed, inclusive).

        Returns:
            List of PIL Image objects, one per extracted page.
        """
        pdf_path_obj = self.validate_pdf(pdf_path)
        
        # Get total pages for validation
        total_pages = self.get_page_count(str(pdf_path_obj))
        actual_end_page = end_page if end_page is not None else total_pages

        # Validate range
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
            f"Extracting pages {start_page}-{actual_end_page} from {pdf_path_obj.name} "
            f"at {self.dpi} DPI (Cropping: {self.enable_cropping})"
        )

        try:
            # Convert PDF to list of PIL Images
            # pdf2image uses 1-based indexing for first_page and last_page
            images = convert_from_path(
                str(pdf_path_obj),
                dpi=self.dpi,
                first_page=start_page,
                last_page=actual_end_page,
                fmt="jpeg",  # JPEG matches VLMClient expectation better usually, though PNG is fine
                thread_count=4
            )

            final_images = []
            
            # Post-process images (cropping)
            for _, img in enumerate(images):
                if self.enable_cropping and self.cropper:
                    # Convert PIL -> Numpy (RGB)
                    img_np = np.array(img)
                    
                    # Convert RGB (PIL) to BGR (cv2) for correct color handling if needed,
                    # but crop logic works on grayscale/luminance mostly. 
                    # However, cv2 usually expects BGR. 
                    # PIL is RGB.
                    img_bgr = img_np[:, :, ::-1].copy() 
                    
                    # Crop
                    cropped_bgr = self.cropper.crop(img_bgr)
                    
                    # Convert filtered BGR back to RGB
                    cropped_rgb = cropped_bgr[:, :, ::-1].copy()
                    
                    # Convert Numpy -> PIL
                    final_img = Image.fromarray(cropped_rgb)
                    final_images.append(final_img)
                else:
                    final_images.append(img)

            logger.success(f"Extracted and processed {len(final_images)} page(s)")
            return final_images

        except Exception as e:
            raise ParsingError(f"Failed to extract pages with pdf2image: {e}") from e

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
        """
        # Validate and get page count (implicit in extract_pages_as_images)
        # But we verify path first
        self.validate_pdf(pdf_path)
        
        # Extract pages as images (handles extraction + cropping)
        images = self.extract_pages_as_images(
            pdf_path,
            start_page=start_page,
            end_page=end_page,
        )

        # Parse each page with VLM
        markdown_pages: list[str] = []
        start_index = start_page 

        for idx, img in enumerate(images):
            current_page_num = start_index + idx
            try:
                with Timer() as t:
                    markdown = await self.parser.generate_with_image(
                        image=img,
                        system_prompt=PARSER_SYSTEM_PROMPT,
                        user_prompt=PARSER_USER_PROMPT,
                    )
                clean_markdown = self._extract_markdown(markdown)
                markdown_pages.append(clean_markdown)
                logger.info(f"Page {current_page_num} parsed successfully in {t.elapsed_str}")

            except Exception as e:
                raise ParsingError(f"VLM parsing failed on page {current_page_num}: {e}") from e

        logger.success(f"Parsed {len(markdown_pages)} page(s) successfully")
        return markdown_pages
