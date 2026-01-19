from pathlib import Path

import fitz
import cv2
import numpy as np
from loguru import logger
from PIL import Image

from ..core.exception import ParsingError, ValidationError
from .crop import ContentCroper
from .image_utils import (
    auto_correct_orientation,
    resize_image,
)
from .prompt import (
    PARSER_SYSTEM_PROMPT,
    PARSER_USER_PROMPT,
)
from .llm_client import VLMClient
from ..utils.timing import Timer


class DocumentParser:
    """
    PDF parser using VLM for document-to-markdown conversion.

    This class provides:
    - PDF validation and page count retrieval
    - High-quality page rasterization using fitz (PyMuPDF)
    - Intelligent auto-rotation and orientation correction
    - Intelligent whitespace cropping
    - Smart resizing for VLM optimization
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
        Extract PDF pages as images using fitz (PyMuPDF).

        Applies auto-rotation, cropping (if enabled), and resizing.

        Args:
            pdf_path: Path to the PDF file.
            start_page: First page to extract (1-indexed, inclusive).
            end_page: Last page to extract (1-indexed, inclusive).

        Returns:
            List of PIL Image objects, one per extracted page.
        """
        pdf_path_obj = self.validate_pdf(pdf_path)
        
        # Calculate zoom based on DPI (72 dpi is default scale=1.0)
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        try:
            doc = fitz.open(str(pdf_path_obj))
            total_pages = len(doc)
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
                f"at {self.dpi} DPI (zoom={zoom:.2f}, Cropping: {self.enable_cropping})"
            )

            final_images = []

            # Loop through pages (0-indexed in fitz)
            for i in range(start_page - 1, actual_end_page):
                page = doc[i]
                
                # Render page
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                # Convert to numpy (buffer -> flat array -> reshape)
                # pix.samples matches the pix.n channels
                img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                
                # Convert to BGR for OpenCV processing
                if pix.n == 4:  # RGBA
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
                elif pix.n == 3:  # RGB
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                
                # Auto-rotate
                img_rotated = auto_correct_orientation(img_np)
                
                # Crop
                if self.enable_cropping and self.cropper:
                    img_cropped = self.cropper.crop(img_rotated)
                else:
                    img_cropped = img_rotated
                
                # Resize (post-crop zoom/resize)
                img_resized = resize_image(img_cropped)
                
                # Convert BGR back to RGB for PIL
                img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                
                # Convert to PIL Image
                final_img = Image.fromarray(img_rgb)
                final_images.append(final_img)

            doc.close()
            logger.success(f"Extracted and processed {len(final_images)} page(s)")
            return final_images

        except Exception as e:
            raise ParsingError(f"Failed to extract pages with fitz: {e}") from e

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
        
        # Extract pages as images (handles extraction + cropping + rotation)
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
