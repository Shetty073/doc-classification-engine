import asyncio
from datetime import datetime, timezone
import logging
from arq.connections import RedisSettings
from sqlalchemy import select, update
from app.classifier import classifier_service
from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Document, DocumentStatus
from app.ocr import ocr_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arq_worker")


async def startup(ctx: dict):
    logger.info("Initializing ARQ background worker for Indian Document Classification...")
    # Pre-warm or verify OCR engine in thread
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, ocr_service._get_engine)
        logger.info("OCR engine pre-warmed successfully.")
    except Exception as e:
        logger.warning("Could not pre-warm OCR engine: %s", e)


async def shutdown(ctx: dict):
    logger.info("Shutting down ARQ background worker...")


async def process_document(ctx: dict, document_id: str, file_path: str):
    """
    Main asynchronous worker job for document processing pipeline:
    1. Updates DB status to PROCESSING.
    2. Runs image/PDF through PaddleOCR to extract text (offloaded to threadpool).
    3. Constructs prompt with OCR text and strict Indian Banking taxonomy.
    4. Makes HTTP POST request to local llama.cpp server.
    5. Updates DB with classified category and status COMPLETED (or FAILED on error).
    """
    logger.info("Starting processing for document_id=%s, file_path=%s", document_id, file_path)

    async with AsyncSessionLocal() as session:
        # Step 1: Update DB status to PROCESSING
        try:
            stmt = (
                update(Document)
                .where(Document.document_id == document_id)
                .values(
                    status=DocumentStatus.PROCESSING,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.info("Document %s marked as PROCESSING", document_id)
        except Exception as e:
            logger.error("Failed to update status to PROCESSING for %s: %s", document_id, e)
            await session.rollback()
            raise

        try:
            # Step 2: Extract text using PaddleOCR in a background thread to keep event loop responsive
            logger.info("Extracting OCR text from %s...", file_path)
            extracted_text = await asyncio.to_thread(ocr_service.extract_text, file_path)

            # Step 3 & 4: Call LLM inference (llama.cpp) to classify document according to strict taxonomy
            logger.info("Classifying extracted text via llama.cpp for document %s...", document_id)
            classification = await classifier_service.classify_text(extracted_text)

            logger.info(
                "Document %s classified as '%s' (Confidence: %.2f, Reasoning: %s)",
                document_id,
                classification.category,
                classification.confidence,
                classification.reasoning,
            )

            # Step 5: Update DB with category, confidence_score, guess, and status COMPLETED
            update_stmt = (
                update(Document)
                .where(Document.document_id == document_id)
                .values(
                    status=DocumentStatus.COMPLETED,
                    category=classification.category,
                    confidence_score=classification.confidence_score,
                    guess=classification.guess,
                    raw_text=extracted_text,
                    error_message=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(update_stmt)
            await session.commit()
            logger.info(
                "Document %s COMPLETED (Category: %s, Score: %s/100, Guess: %s)",
                document_id,
                classification.category,
                classification.confidence_score,
                classification.guess,
            )

        except Exception as e:
            logger.error("Pipeline failure for document %s: %s", document_id, e, exc_info=True)
            await session.rollback()
            # Update DB with FAILED status
            fail_stmt = (
                update(Document)
                .where(Document.document_id == document_id)
                .values(
                    status=DocumentStatus.FAILED,
                    error_message=str(e),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(fail_stmt)
            await session.commit()
            raise


class WorkerSettings:
    """Configuration class for the ARQ CLI runner (arq app.worker.WorkerSettings)."""

    functions = [process_document]
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
    )
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300  # 5 minutes
    keep_result = 3600  # 1 hour
