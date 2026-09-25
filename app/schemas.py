from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models import DocumentStatus


# ---------------------------------------------------------
# Auth & User Schemas
# ---------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------
# Document Schemas
# ---------------------------------------------------------
class DocumentUploadResponse(BaseModel):
    document_id: str
    reference_id: str
    status: DocumentStatus
    callback_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BatchUploadItem(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus


class BatchUploadResponse(BaseModel):
    reference_id: str
    total_enqueued: int
    documents: List[BatchUploadItem]


class CompletedDocumentItem(BaseModel):
    document_id: str
    reference_id: str
    file_name: Optional[str] = None
    status: DocumentStatus = DocumentStatus.COMPLETED
    category: Optional[str] = None
    confidence_score: Optional[int] = Field(default=None, ge=1, le=100, description="Confidence score between 1 and 100")
    guess: Optional[str] = Field(default=None, description="Heuristic/LLM guess if document is UNKNOWN")
    extracted_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extracted key-value entities")
    quality_score: Optional[int] = Field(default=None, ge=1, le=100, description="Document image quality score")
    quality_issues: Optional[List[str]] = Field(default=None, description="Quality issue flags")
    document_url: str
    raw_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentStatusSummaryItem(BaseModel):
    document_id: str
    file_name: Optional[str] = None
    status: DocumentStatus
    category: Optional[str] = None
    confidence_score: Optional[int] = Field(default=None, ge=1, le=100, description="Confidence score between 1 and 100")
    guess: Optional[str] = Field(default=None, description="Heuristic/LLM guess if document is UNKNOWN")
    extracted_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extracted key-value entities")
    quality_score: Optional[int] = Field(default=None, ge=1, le=100, description="Document image quality score")
    quality_issues: Optional[List[str]] = Field(default=None, description="Quality issue flags")
    error_message: Optional[str] = None
    raw_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReferenceStatusResponse(BaseModel):
    reference_id: str
    total_count: int
    counts_by_status: Dict[str, int]
    documents: List[DocumentStatusSummaryItem]


# ---------------------------------------------------------
# OCR & Classifier Schemas
# ---------------------------------------------------------
class ClassificationResult(BaseModel):
    category: str
    confidence_score: int = Field(default=85, ge=1, le=100, description="Confidence score between 1 and 100")
    guess: Optional[str] = Field(default=None, description="Hypothesis/guess of document type if category is UNKNOWN")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    sub_category: Optional[str] = None
    extracted_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured extracted entities")
