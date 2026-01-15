import cv2
import numpy as np


class ContentCroper:
    """
    Intelligent image cropper for document pages.

    Uses horizontal and vertical projection profiles to identify and crop
    the main content area, ignoring headers/footers and whitespace.

    Attributes:
        padding (int): Padding to add around the cropped content in pixels.
        ignore_bottom_percent (float): Percentage of bottom area to ignore (footer).
        footer_gap_threshold (int): Minimum gap size to consider as header/footer separation.
        column_ink_ratio (float): Threshold ratio for vertical projection (column detection).
        row_ink_ratio (float): Threshold ratio for horizontal projection (row detection).
    """

    def __init__(
        self,
        padding: int = 10,
        ignore_bottom_percent: float = 12.0,
        footer_gap_threshold: int = 100,
        column_ink_ratio: float = 0.01,
        row_ink_ratio: float = 0.002,
    ):
        """
        Initialize the cropper with configuration parameters.

        Args:
            padding: Pixels to pad the result. Defaults to 10.
            ignore_bottom_percent: Percentage of image height to ignore at bottom.
                Defaults to 12.0.
            footer_gap_threshold: Vertical gap size (pixels) that separates
                main content from footer/header. Defaults to 100.
            column_ink_ratio: Min ratio of dark pixels to height for vertical bounds.
                Defaults to 0.01.
            row_ink_ratio: Min ratio of dark pixels to width for horizontal bounds.
                Defaults to 0.002.
        """
        self.padding = padding
        self.ignore_bottom_percent = ignore_bottom_percent
        self.footer_gap_threshold = footer_gap_threshold
        self.column_ink_ratio = column_ink_ratio
        self.row_ink_ratio = row_ink_ratio

    def _find_main_content_block(self, h_proj: np.ndarray) -> tuple[int, int]:
        """
        Identify the main content block from horizontal projection.

        Detects large vertical gaps to distinguish the main body from
        headers and footers. Returns the largest continuous block.

        Args:
            h_proj: Horizontal projection array (sum of pixels per row).

        Returns:
            Tuple of (top_index, bottom_index) defining the main content vertical bounds.
        """
        idx = np.where(h_proj > 0)[0]
        if len(idx) == 0:
            return 0, len(h_proj) - 1

        gaps = np.diff(idx)
        large_gaps = np.where(gaps > self.footer_gap_threshold)[0]

        if len(large_gaps) == 0:
            return idx[0], idx[-1]

        blocks = []
        start = 0
        for g in large_gaps:
            block = idx[start : g + 1]
            blocks.append((block[0], block[-1], len(block)))
            start = g + 1

        block = idx[start:]
        blocks.append((block[0], block[-1], len(block)))

        # Return the block with the most vertical content (height)
        top, bottom, _ = max(blocks, key=lambda x: x[2])
        return top, bottom

    def _projection_bounds(self, proj: np.ndarray, min_pixels: int) -> tuple[int, int] | None:
        """
        Find start and end indices where projection exceeds threshold.

        Args:
            proj: Projection array (horizontal or vertical).
            min_pixels: Minimum pixel count threshold.

        Returns:
            Tuple of (start, end) indices, or None if no content found.
        """
        idx = np.where(proj > min_pixels)[0]
        if len(idx) == 0:
            return None
        return idx[0], idx[-1]

    def crop(self, image: np.ndarray) -> np.ndarray:
        """
        Crop the image to the main content area.

        Performs a two-pass cropping:
        1. Base crop using projection profiles and gap detection to remove
           large headers/footers and margins.
        2. Fine crop on the result to diligently remove remaining whitespace.

        Args:
            image: Input image as numpy array (BGR or Grayscale).

        Returns:
            Cropped image as numpy array.
        """
        h, w = image.shape[:2]

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        h_proj = np.sum(binary > 0, axis=1)
        v_proj = np.sum(binary > 0, axis=0)

        # Ignore footer area based on percentage
        if self.ignore_bottom_percent > 0:
            cut = int(h * self.ignore_bottom_percent / 100)
            h_proj[-cut:] = 0

        # Calculate adaptive thresholds
        min_row_pixels = int(w * self.row_ink_ratio)
        min_col_pixels = int(h * self.column_ink_ratio)

        tb = self._projection_bounds(h_proj, min_row_pixels)
        lr = self._projection_bounds(v_proj, min_col_pixels)

        if not tb or not lr:
            return image

        top, bottom = tb
        left, right = lr

        # Use gap detection to identify main content (avoids header/footer)
        top, bottom = self._find_main_content_block(h_proj)

        # Apply padding
        top = max(0, top - self.padding)
        bottom = min(h, bottom + self.padding)
        left = max(0, left - self.padding)
        right = min(w, right + self.padding)

        cropped = image[top:bottom, left:right]

        gray2 = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        _, bin2 = cv2.threshold(gray2, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        h2, w2 = bin2.shape
        v2 = np.sum(bin2 > 0, axis=0)
        h2p = np.sum(bin2 > 0, axis=1)

        min_col2 = int(h2 * self.column_ink_ratio)
        min_row2 = int(w2 * self.row_ink_ratio)

        lr2 = self._projection_bounds(v2, min_col2)
        tb2 = self._projection_bounds(h2p, min_row2)

        if lr2 and tb2:
            l2, r2 = lr2
            t2, b2 = tb2
            cropped = cropped[t2:b2, l2:r2]

        return cropped
