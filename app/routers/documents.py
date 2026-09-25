import os
import re
import uuid
from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.models import Document, DocumentStatus, User
from app.schemas import (
    BatchUploadItem,
    BatchUploadResponse,
    CompletedDocumentItem,
    DocumentStatusSummaryItem,
    DocumentUploadResponse,
    ReferenceStatusResponse,
)
from app.security import get_current_user

router = APIRouter(tags=["Documents"])


def sanitize_filename(filename: str) -> str:
    """Sanitizes filename to prevent directory traversal or malformed paths."""
    clean = os.path.basename(filename)
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean)
    return clean or "document"


async def _save_upload_file(file: UploadFile, unique_doc_id: str) -> str:
    """Safely streams an upload file to disk while enforcing path containment and size limit."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must not be empty.",
        )

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    safe_filename = sanitize_filename(file.filename)
    stored_filename = f"{unique_doc_id}_{safe_filename}"
    file_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, stored_filename))

    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    if not file_path.startswith(upload_root):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path detected.",
        )

    bytes_written = 0
    chunk_size = 1024 * 1024  # 1MB chunks
    try:
        with open(file_path, "wb") as destination:
            while chunk := await file.read(chunk_size):
                bytes_written += len(chunk)
                if bytes_written > settings.MAX_FILE_SIZE_BYTES:
                    destination.close()
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
                    )
                destination.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file to disk: {exc}",
        )

    return file_path


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload financial document for asynchronous OCR and classification",
)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Document file (PDF or Image)"),
    reference_id: str = Form(..., min_length=1, max_length=64, description="Lending/KYC application reference ID"),
    callback_url: Optional[str] = Form(None, description="Optional webhook URL for completion notification"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a KYC or financial document, stores it securely, creates a PENDING
    record in PostgreSQL, and enqueues an asynchronous processing job to ARQ/Redis.
    """
    unique_doc_id = f"doc_{uuid.uuid4().hex}"
    file_path = await _save_upload_file(file, unique_doc_id)

    new_doc = Document(
        document_id=unique_doc_id,
        reference_id=reference_id,
        file_path=file_path,
        callback_url=callback_url,
        status=DocumentStatus.PENDING,
        category=None,
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    arq_pool = getattr(request.app.state, "arq_redis", None)
    if arq_pool:
        await arq_pool.enqueue_job(
            "process_document",
            document_id=unique_doc_id,
            file_path=file_path,
        )

    return DocumentUploadResponse(
        document_id=new_doc.document_id,
        reference_id=new_doc.reference_id,
        status=new_doc.status,
        callback_url=new_doc.callback_url,
    )


@router.post(
    "/upload-batch",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload multiple financial documents in a single batch",
)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_batch(
    request: Request,
    files: List[UploadFile] = File(..., description="List of document files (PDF or Images)"),
    reference_id: str = Form(..., min_length=1, max_length=64, description="Lending/KYC application reference ID"),
    callback_url: Optional[str] = Form(None, description="Optional webhook URL for notifications"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a batch of KYC and lending documents under a single reference ID,
    streams them to storage, creates PENDING records, and dispatches parallel ARQ jobs.
    """
    if not files or len(files) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided in batch upload.")

    if len(files) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 20 files allowed per batch upload.")

    enqueued_items = []
    arq_pool = getattr(request.app.state, "arq_redis", None)

    for upload_file in files:
        unique_doc_id = f"doc_{uuid.uuid4().hex}"
        file_path = await _save_upload_file(upload_file, unique_doc_id)

        new_doc = Document(
            document_id=unique_doc_id,
            reference_id=reference_id,
            file_path=file_path,
            callback_url=callback_url,
            status=DocumentStatus.PENDING,
            category=None,
        )
        db.add(new_doc)
        enqueued_items.append((new_doc, upload_file.filename or "unnamed", file_path))

    await db.commit()

    # Enqueue jobs to ARQ
    batch_records = []
    for doc, orig_filename, path in enqueued_items:
        if arq_pool:
            await arq_pool.enqueue_job("process_document", document_id=doc.document_id, file_path=path)
        batch_records.append(
            BatchUploadItem(
                document_id=doc.document_id,
                filename=orig_filename,
                status=DocumentStatus.PENDING,
            )
        )

    return BatchUploadResponse(
        reference_id=reference_id,
        total_enqueued=len(batch_records),
        documents=batch_records,
    )


@router.get(
    "/documents/{reference_id}",
    response_model=List[CompletedDocumentItem],
    summary="List all completed documents for a given reference_id",
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_completed_documents(
    request: Request,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all COMPLETED documents for the given reference_id,
    including document_id, a document_url for secure download, classified category,
    confidence score, guess, extracted metadata, and quality score.
    """
    stmt = (
        select(Document)
        .where(
            Document.reference_id == reference_id,
            Document.status == DocumentStatus.COMPLETED,
        )
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(stmt)
    documents = result.scalars().all()

    base_url = str(request.base_url).rstrip("/")
    response_items = []
    for doc in documents:
        download_url = f"{base_url}/documents/download/{doc.document_id}"
        response_items.append(
            CompletedDocumentItem(
                document_id=doc.document_id,
                reference_id=doc.reference_id,
                category=doc.category,
                confidence_score=doc.confidence_score,
                guess=doc.guess,
                extracted_metadata=doc.extracted_metadata,
                quality_score=doc.quality_score,
                quality_issues=doc.quality_issues,
                document_url=download_url,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
        )

    return response_items


@router.get(
    "/documents/{reference_id}/status",
    response_model=ReferenceStatusResponse,
    summary="Get processing status overview of all documents for reference_id",
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_reference_documents_status(
    request: Request,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns processing status of all documents associated with the reference_id
    including total count and counts breakdown by status (PENDING, PROCESSING, COMPLETED, FAILED).
    """
    doc_stmt = (
        select(Document)
        .where(Document.reference_id == reference_id)
        .order_by(Document.created_at.desc())
    )
    doc_result = await db.execute(doc_stmt)
    documents = doc_result.scalars().all()

    count_stmt = (
        select(Document.status, func.count(Document.id))
        .where(Document.reference_id == reference_id)
        .group_by(Document.status)
    )
    count_result = await db.execute(count_stmt)
    status_counts_map = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in count_result.all()}

    counts_by_status = {
        DocumentStatus.PENDING.value: status_counts_map.get(DocumentStatus.PENDING.value, 0),
        DocumentStatus.PROCESSING.value: status_counts_map.get(DocumentStatus.PROCESSING.value, 0),
        DocumentStatus.COMPLETED.value: status_counts_map.get(DocumentStatus.COMPLETED.value, 0),
        DocumentStatus.FAILED.value: status_counts_map.get(DocumentStatus.FAILED.value, 0),
    }

    doc_items = [
        DocumentStatusSummaryItem(
            document_id=d.document_id,
            status=d.status,
            category=d.category,
            confidence_score=d.confidence_score,
            guess=d.guess,
            extracted_metadata=d.extracted_metadata,
            quality_score=d.quality_score,
            quality_issues=d.quality_issues,
            error_message=d.error_message,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in documents
    ]

    return ReferenceStatusResponse(
        reference_id=reference_id,
        total_count=len(documents),
        counts_by_status=counts_by_status,
        documents=doc_items,
    )


@router.get(
    "/documents/download/{document_id}",
    summary="Secure download of uploaded document",
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def download_document(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Validates token and securely streams the document file back to authorized banking client.
    """
    stmt = select(Document).where(Document.document_id == document_id)
    result = await db.execute(stmt)
    doc = result.scalars().first()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    if not os.path.exists(doc.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file missing from storage.",
        )

    filename = os.path.basename(doc.file_path)
    return FileResponse(
        path=doc.file_path,
        filename=filename,
        content_disposition_type="inline",
    )
