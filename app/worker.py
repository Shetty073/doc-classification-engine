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
from app.utils.quality import assess_document_quality
from app.utils.redactor import mask_aadhaar_numbers
from app.utils.webhook import dispatch_webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arq_worker")


async def startup(ctx: dict):
    logger.info("Initializing ARQ background worker for Indian Document Classification...")
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
    2. Runs quality & blur analysis (Laplacian variance, resolution check).
    3. Runs OCR extraction (hybrid PyMuPDF / PaddleOCR GPU/CPU).
    4. Applies UIDAI & RBI compliant Aadhaar masking to raw OCR text.
    5. Classifies document via LLM / Banking Taxonomy and extracts entities.
    6. Persists result (status, category, confidence, guess, entities, quality).
    7. Dispatches signed webhook callback if callback_url was specified.
    """
    logger.info("Starting processing for document_id=%s, file_path=%s", document_id, file_path)

    async with AsyncSessionLocal() as session:
        # Step 1: Update DB status to PROCESSING and retrieve callback_url
        callback_url = None
        reference_id = None
        try:
            sel_stmt = select(Document).where(Document.document_id == document_id)
            res = await session.execute(sel_stmt)
            doc_record = res.scalars().first()
            if doc_record:
                callback_url = doc_record.callback_url
                reference_id = doc_record.reference_id

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
            # Step 2: Quality & Blur Assessment
            logger.info("Running quality & tampering assessment on %s...", file_path)
            quality_score, quality_issues = await asyncio.to_thread(assess_document_quality, file_path)
            logger.info("Document %s Quality: %d/100, Issues: %s", document_id, quality_score, quality_issues)

            # Step 3: Extract text using PaddleOCR in background thread
            logger.info("Extracting OCR text from %s...", file_path)
            raw_extracted_text = await asyncio.to_thread(ocr_service.extract_text, file_path)

            # Step 4: Regulatory Aadhaar Masking (UIDAI / RBI Section 16 compliance)
            masked_text = mask_aadhaar_numbers(raw_extracted_text)

            # Step 5: Classify text and extract key financial entities
            logger.info("Classifying document %s via banking taxonomy...", document_id)
            classification = await classifier_service.classify_text(masked_text)

            logger.info(
                "Document %s classified as '%s' (Score: %d/100, Reasoning: %s)",
                document_id,
                classification.category,
                classification.confidence_score,
                classification.reasoning,
            )

            # Step 6: Update DB with category, confidence, guess, entities, quality metrics
            completed_time = datetime.now(timezone.utc)
            update_stmt = (
                update(Document)
                .where(Document.document_id == document_id)
                .values(
                    status=DocumentStatus.COMPLETED,
                    category=classification.category,
                    confidence_score=classification.confidence_score,
                    guess=classification.guess,
                    extracted_metadata=classification.extracted_metadata,
                    quality_score=quality_score,
                    quality_issues=quality_issues,
                    raw_text=masked_text,
                    error_message=None,
                    updated_at=completed_time,
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

            # Step 7: Dispatch Webhook Event if callback_url is configured
            if callback_url:
                webhook_payload = {
                    "event": "document.completed",
                    "document_id": document_id,
                    "reference_id": reference_id,
                    "status": "COMPLETED",
                    "category": classification.category,
                    "confidence_score": classification.confidence_score,
                    "guess": classification.guess,
                    "extracted_metadata": classification.extracted_metadata,
                    "quality_score": quality_score,
                    "quality_issues": quality_issues,
                    "completed_at": completed_time.isoformat(),
                }
                asyncio.create_task(dispatch_webhook(callback_url, webhook_payload))

        except Exception as e:
            logger.error("Pipeline failure for document %s: %s", document_id, e, exc_info=True)
            await session.rollback()
            failed_time = datetime.now(timezone.utc)
            fail_stmt = (
                update(Document)
                .where(Document.document_id == document_id)
                .values(
                    status=DocumentStatus.FAILED,
                    error_message=str(e),
                    updated_at=failed_time,
                )
            )
            await session.execute(fail_stmt)
            await session.commit()

            if callback_url:
                webhook_payload = {
                    "event": "document.failed",
                    "document_id": document_id,
                    "reference_id": reference_id,
                    "status": "FAILED",
                    "error_message": str(e),
                    "failed_at": failed_time.isoformat(),
                }
                asyncio.create_task(dispatch_webhook(callback_url, webhook_payload))

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
