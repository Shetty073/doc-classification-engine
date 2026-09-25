from datetime import datetime
from typing import Dict, List, Optional
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

    model_config = ConfigDict(from_attributes=True)


class CompletedDocumentItem(BaseModel):
    document_id: str
    reference_id: str
    category: Optional[str] = None
    document_url: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentStatusSummaryItem(BaseModel):
    document_id: str
    status: DocumentStatus
    category: Optional[str] = None
    error_message: Optional[str] = None
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
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    sub_category: Optional[str] = None
