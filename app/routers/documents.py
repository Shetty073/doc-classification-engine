import os
import re
import uuid
from typing import List
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
    # Remove all characters except alphanumeric, dashes, underscores, and dots
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean)
    return clean or "document"


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a KYC or financial document, stores it securely, creates a PENDING
    record in PostgreSQL, and enqueues an asynchronous processing job to ARQ/Redis.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must not be empty.",
        )

    # 1. Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    # 2. Generate secure document identifiers and save path
    unique_doc_id = f"doc_{uuid.uuid4().hex}"
    safe_filename = sanitize_filename(file.filename)
    stored_filename = f"{unique_doc_id}_{safe_filename}"
    file_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, stored_filename))

    # Ensure target path stays strictly inside UPLOAD_DIR
    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    if not file_path.startswith(upload_root):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path detected.",
        )

    # 3. Stream file to disk while enforcing max file size
    bytes_written = 0
    chunk_size = 1024 * 1024  # 1MB chunk
    try:
        with open(file_path, "wb") as destination:
            while chunk := await file.read(chunk_size):
                bytes_written += len(chunk)
                if bytes_written > settings.MAX_FILE_SIZE_BYTES:
                    # Clean up file on breach
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

    # 4. Insert record into PostgreSQL with PENDING status
    new_doc = Document(
        document_id=unique_doc_id,
        reference_id=reference_id,
        file_path=file_path,
        status=DocumentStatus.PENDING,
        category=None,
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    # 5. Enqueue background processing job to ARQ via Redis
    arq_pool = getattr(request.app.state, "arq_redis", None)
    if arq_pool:
        await arq_pool.enqueue_job(
            "process_document",
            document_id=unique_doc_id,
            file_path=file_path,
        )
    else:
        # Fallback if ARQ redis pool is temporarily detached (logs warning)
        import logging
        logging.getLogger("api").warning(
            "ARQ redis connection pool not attached to app.state. Job %s pending manual worker pickup.",
            unique_doc_id,
        )

    return DocumentUploadResponse(
        document_id=new_doc.document_id,
        reference_id=new_doc.reference_id,
        status=new_doc.status,
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
    including document_id, a document_url for secure download, and the classified category.
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
    # 1. Fetch document items
    doc_stmt = (
        select(Document)
        .where(Document.reference_id == reference_id)
        .order_by(Document.created_at.desc())
    )
    doc_result = await db.execute(doc_stmt)
    documents = doc_result.scalars().all()

    # 2. Calculate counts by status
    count_stmt = (
        select(Document.status, func.count(Document.id))
        .where(Document.reference_id == reference_id)
        .group_by(Document.status)
    )
    count_result = await db.execute(count_stmt)
    status_counts_map = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in count_result.all()}

    # Initialize all enum keys so caller always has predictable structure
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

    # Determine media type based on extension
    filename = os.path.basename(doc.file_path)
    return FileResponse(
        path=doc.file_path,
        filename=filename,
        content_disposition_type="inline",
    )
