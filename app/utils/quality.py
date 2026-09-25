"""
Document Quality and Anti-Tampering Assessment Engine.
Analyzes resolution, contrast, and image sharpness (Laplacian variance)
to flag blurry, low-resolution, or degraded document scans.
"""
import os
from typing import List, Tuple
import numpy as np
from PIL import Image
import fitz  # PyMuPDF


def _compute_laplacian_variance(gray_array: np.ndarray) -> float:
    """
    Computes variance of the Laplacian filter using discrete 2nd order differences.
    Standard computer vision measure of edge sharpness and blurriness.
    """
    # 3x3 discrete Laplacian kernel convolution approximation via slicing
    # [ 0,  1,  0]
    # [ 1, -4,  1]
    # [ 0,  1,  0]
    h, w = gray_array.shape
    if h < 5 or w < 5:
        return 0.0

    center = gray_array[1 : h - 1, 1 : w - 1]
    top = gray_array[0 : h - 2, 1 : w - 1]
    bottom = gray_array[2:h, 1 : w - 1]
    left = gray_array[1 : h - 1, 0 : w - 2]
    right = gray_array[1 : h - 1, 2:w]

    laplacian = top + bottom + left + right - 4.0 * center
    return float(np.var(laplacian))


def assess_document_quality(file_path: str) -> Tuple[int, List[str]]:
    """
    Evaluates image or first page of PDF for quality metrics:
    - Resolution / Dimensions
    - Contrast distribution
    - Sharpness / Blur score
    Returns (quality_score: 1-100, quality_issues: List[str])
    """
    issues: List[str] = []
    base_score = 100

    if not os.path.exists(file_path):
        return 10, ["FILE_NOT_FOUND"]

    ext = os.path.splitext(file_path)[1].lower()
    pil_image = None

    try:
        if ext == ".pdf":
            # Extract first page as image using PyMuPDF
            doc = fitz.open(file_path)
            if len(doc) == 0:
                return 10, ["EMPTY_PDF"]
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()
        else:
            pil_image = Image.open(file_path).convert("RGB")

        width, height = pil_image.size

        # 1. Resolution Check
        if width < 500 or height < 500:
            issues.append("LOW_RESOLUTION")
            base_score -= 25
        elif width < 800 or height < 800:
            issues.append("MODERATE_RESOLUTION")
            base_score -= 10

        # Convert to grayscale numpy array for vision analysis
        gray = pil_image.convert("L")
        gray_arr = np.array(gray, dtype=np.float32)

        # 2. Contrast & Dynamic Range Check
        std_dev = float(np.std(gray_arr))
        if std_dev < 20.0:
            issues.append("EXTREME_LOW_CONTRAST_OR_BLANK")
            base_score -= 40
        elif std_dev < 35.0:
            issues.append("POOR_CONTRAST_OR_GLARE")
            base_score -= 15

        # 3. Blur Detection (Laplacian Variance)
        lap_var = _compute_laplacian_variance(gray_arr)
        if lap_var < 50.0:
            issues.append("HEAVY_BLUR_DETECTED")
            base_score -= 30
        elif lap_var < 100.0:
            issues.append("MILD_BLUR")
            base_score -= 10

    except Exception as exc:
        issues.append(f"QUALITY_ANALYSIS_FAILED_{type(exc).__name__}")
        base_score = 50
    finally:
        if pil_image:
            pil_image.close()

    final_score = max(1, min(100, base_score))
    return final_score, issues
