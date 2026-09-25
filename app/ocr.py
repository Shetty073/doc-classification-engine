import os
import logging
from typing import List
from app.config import settings

logger = logging.getLogger("ocr_service")


class OCRService:
    _instance = None
    _engine = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OCRService, cls).__new__(cls)
        return cls._instance

    def _get_engine(self, force_cpu: bool = False):
        """Lazy loader for PaddleOCR with automated GPU-to-CPU fallback."""
        use_gpu = settings.PADDLE_OCR_USE_GPU and not force_cpu

        if self._engine is None or (force_cpu and getattr(self, "_is_gpu", False)):
            try:
                from paddleocr import PaddleOCR

                logger.info(
                    "Initializing PaddleOCR engine (lang=%s, use_gpu=%s)...",
                    settings.PADDLE_OCR_LANG,
                    use_gpu,
                )
                self._engine = PaddleOCR(
                    use_angle_cls=True,
                    lang=settings.PADDLE_OCR_LANG,
                    use_gpu=use_gpu,
                    show_log=False,
                )
                self._is_gpu = use_gpu
                logger.info("PaddleOCR engine initialized successfully (use_gpu=%s).", use_gpu)
            except Exception as e:
                if use_gpu:
                    logger.warning("Failed to initialize PaddleOCR on GPU (%s). Gracefully falling back to CPU.", e)
                    return self._get_engine(force_cpu=True)
                logger.error("Error creating PaddleOCR instance: %s", e)
                raise
        return self._engine

    def extract_text(self, file_path: str) -> str:
        """
        Extracts structured plain text from images or PDF documents.
        Handles multi-line grouping and page iteration.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found for OCR: {file_path}")

        engine = self._get_engine()
        ext = os.path.splitext(file_path)[1].lower()
        extracted_lines: List[str] = []

        try:
            if ext == ".pdf":
                extracted_lines = self._process_pdf(file_path, engine)
            else:
                extracted_lines = self._process_image(file_path, engine)
        except Exception as exc:
            logger.error("Failed during OCR extraction on file %s: %s", file_path, exc, exc_info=True)
            raise

        full_text = "\n".join(extracted_lines).strip()
        logger.info("OCR completed for %s. Extracted %d characters across %d lines.",
                    file_path, len(full_text), len(extracted_lines))
        return full_text

    def _process_image(self, file_path: str, engine) -> List[str]:
        lines: List[str] = []
        try:
            result = engine.ocr(file_path, cls=True)
        except Exception as ocr_err:
            err_msg = str(ocr_err).lower()
            if "cudnn" in err_msg or "cuda" in err_msg or "gpu" in err_msg or "precondition" in err_msg:
                logger.warning("GPU execution failed at runtime (%s). Retrying image with CPU engine...", ocr_err)
                cpu_engine = self._get_engine(force_cpu=True)
                result = cpu_engine.ocr(file_path, cls=True)
            else:
                raise

        if not result or result[0] is None:
            return lines

        # PaddleOCR returns [[[coords], (text, confidence)], ...]
        for page in result:
            if page is None:
                continue
            for line in page:
                if line and len(line) >= 2 and len(line[1]) >= 1:
                    text_str = str(line[1][0]).strip()
                    if text_str:
                        lines.append(text_str)
        return lines

    def _process_pdf(self, file_path: str, engine) -> List[str]:
        """
        Processes PDF by extracting text from key first pages using digital PDF text
        or rasterized page OCR via PyMuPDF. Caps extraction to first 5 pages for enterprise speed.
        """
        lines: List[str] = []

        # 1. Fast digital PDF text extraction (first 5 pages)
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            digital_text = []
            max_pages = min(len(reader.pages), 5)
            for idx in range(max_pages):
                page = reader.pages[idx]
                page_text = page.extract_text()
                if page_text and len(page_text.strip()) > 30:
                    digital_text.append(page_text.strip())

            if digital_text and len("\n".join(digital_text)) > 60:
                logger.info("Extracted digital text from first %d pages of %s", max_pages, file_path)
                return ["\n".join(digital_text)]
        except Exception as pdf_err:
            logger.debug("Digital PDF extraction skipped/failed: %s", pdf_err)

        # 2. Rasterized OCR using PyMuPDF (first 3 pages for scanned documents)
        try:
            import pymupdf  # PyMuPDF
            doc = pymupdf.open(file_path)
            max_ocr_pages = min(len(doc), 3)
            for page_num in range(max_ocr_pages):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                temp_png = f"{file_path}_temp_page_{page_num}.png"
                pix.save(temp_png)
                try:
                    page_lines = self._process_image(temp_png, engine)
                    lines.extend(page_lines)
                finally:
                    if os.path.exists(temp_png):
                        os.remove(temp_png)
        except Exception as ocr_err:
            logger.error("Failed to rasterize and OCR PDF %s: %s", file_path, ocr_err)
            raise

        return lines


ocr_service = OCRService()
