import cv2
import math
import numpy as np
from loguru import logger

def rotate_image(img: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotate image by arbitrary angle (for small adjustments).
    
    Args:
        img: Input image
        angle: Rotation angle in degrees (positive = counterclockwise)
    
    Returns:
        Rotated image
    """
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    
    # Get rotation matrix
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    
    # Calculate new image bounds
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    
    # Adjust translation
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]
    
    # Perform rotation
    rotated = cv2.warpAffine(
        img, M, (new_w, new_h), 
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255)
    )
    
    return rotated

def _smooth_projection(projection: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """
    Smooth 1D projection array using Gaussian blur.
    
    Args:
        projection: 1D numpy array.
        sigma: Gaussian sigma.
        
    Returns:
        Smoothed array.
    """
    if len(projection) == 0:
        return projection
        
    # Calculate kernel size based on sigma (3*sigma rule approximation)
    # ksize must be odd
    ksize = int(2 * math.ceil(2 * sigma) + 1)
    
    # Reshape to (N, 1) for vertical smoothing
    # Note: cv2.GaussianBlur(src, ksize, sigmaX, sigmaY)
    # We want valid response over the array.
    smoothed = cv2.GaussianBlur(
        projection.astype(np.float32).reshape(-1, 1), 
        (1, ksize), 
        0, 
        sigmaY=sigma
    )
    return smoothed.flatten()

def score_orientation(img: np.ndarray) -> float:
    """
    Enhanced scoring with noise resistance to determine correct orientation.
    Higher score means more likely to be the correct "upright" orientation.
    """
    h, w = img.shape[:2]
    
    # Convert to grayscale if needed
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
        
    # Denoise BEFORE analysis
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # More aggressive threshold
    _, binary = cv2.threshold(
        gray, 0, 255, 
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    
    # Morphological cleaning (remove small noise)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    # Factor 1: Top-heavy (text usually starts at top)
    top_third = binary[:h//3, :]
    middle_third = binary[h//3:2*h//3, :]
    bottom_third = binary[2*h//3:, :]
    
    top_density = np.sum(top_third) / max(top_third.size, 1)
    middle_density = np.sum(middle_third) / max(middle_third.size, 1)
    bottom_density = np.sum(bottom_third) / max(bottom_third.size, 1)
    
    # Improved: Consider middle too (more stable)
    top_heavy_score = (top_density + middle_density * 0.5) / (bottom_density + 1e-6)
    
    # Factor 2: Horizontal projection variance
    projection = np.sum(binary, axis=1)
    
    # Smooth projection to reduce noise impact
    projection = _smooth_projection(projection, sigma=2)
    
    variance_score = np.var(projection) / 1000
    
    # Factor 3: Detect large text blocks at top
    # Improved: Filter by aspect ratio (text blocks are usually wider)
    contours, _ = cv2.findContours(
        top_third, 
        cv2.RETR_EXTERNAL, 
        cv2.CHAIN_APPROX_SIMPLE
    )
    
    header_blocks = 0
    for c in contours:
        area = cv2.contourArea(c)
        if area > 500:  # Minimum size
            x, y, w_cont, h_cont = cv2.boundingRect(c)
            aspect_ratio = w_cont / (h_cont + 1e-6)
            
            # Text blocks usually wider than tall
            if aspect_ratio > 2:
                header_blocks += 1
    
    header_score = header_blocks / 10
    
    # Weighted combination with bounds
    total_score = (
        min(top_heavy_score, 5.0) * 0.5 +  # Cap extreme values
        min(variance_score, 2.0) * 0.3 +
        min(header_score, 1.0) * 0.2
    )
    
    return total_score

def auto_correct_orientation(img: np.ndarray) -> np.ndarray:
    """
    Detect and correct image orientation using Hough lines and content scoring.
    """
    # Pre-process to reduce noise impact
    # Downsample if too large (speeds up + reduces noise)
    h, w = img.shape[:2]
    analysis_img = img
    
    if max(h, w) > 1500:
        scale = 1500 / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        analysis_img = cv2.resize(
            img, (new_w, new_h), 
            interpolation=cv2.INTER_AREA
        )
    
    # Step 1: Detect angle using Hough (on downsampled)
    gray = cv2.cvtColor(analysis_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    
    if lines is None:
        return img
    
    angles = []
    for line in lines[:50]:
        theta = line[0][1]
        angle = np.degrees(theta) - 90
        # Normalize to -90 to 90
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        angles.append(angle)
    
    if not angles:
        return img

    median_angle = np.median(angles)
    logger.debug(f"Detected angle: {median_angle:.2f}°")
    
    # Step 2: If ~90° rotation needed, use scoring
    if 85 <= abs(median_angle) <= 95:
        # Test both orientations on DOWNSAMPLED image
        test_cw = cv2.rotate(analysis_img, cv2.ROTATE_90_CLOCKWISE)
        test_ccw = cv2.rotate(analysis_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        
        score_cw = score_orientation(test_cw)
        score_ccw = score_orientation(test_ccw)
        
        logger.debug(f"CW score: {score_cw:.3f}, CCW score: {score_ccw:.3f}")
        
        # Require significant difference to rotate
        score_diff = abs(score_cw - score_ccw)
        
        if score_diff < 0.35:
            # Scores too close, don't rotate
            logger.debug("Ambiguous scores, keeping original")
            return img
        
        # Apply rotation to ORIGINAL full-res image
        if score_cw > score_ccw:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        else:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    
    # Step 3: Handle other angles
    elif -5 < median_angle < 5:
        return img
    elif abs(median_angle) > 175:
        return cv2.rotate(img, cv2.ROTATE_180)
    else:
        # Small angle correction
        return rotate_image(img, median_angle)

def resize_image(image: np.ndarray, max_size: int = 2048) -> np.ndarray:
    """
    Resize large images to prevent OOM.
    Most VLMs work best with 1024-2048px.
    
    Args:
        image: Input image (numpy array).
        max_size: Maximum dimension (width or height).
        
    Returns:
        Resized image.
    """
    h, w = image.shape[:2]

    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        # Use INTER_LANCZOS4 for high quality downscaling
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    return image
