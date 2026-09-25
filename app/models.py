import enum
import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SqlEnum,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', is_active={self.is_active})>"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(String(64), unique=True, index=True, nullable=False)
    reference_id = Column(String(64), index=True, nullable=False)
    file_path = Column(String(512), nullable=False)
    status = Column(
        SqlEnum(
            DocumentStatus,
            name="document_status_enum",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    category = Column(String(100), nullable=True, index=True)
    confidence_score = Column(Integer, nullable=True)  # Confidence scale 1 to 100
    guess = Column(String(255), nullable=True)  # Best guess if category is UNKNOWN
    callback_url = Column(String(512), nullable=True)  # Webhook notification URL
    extracted_metadata = Column(JSON, nullable=True)  # Structured extracted entities/fields
    quality_score = Column(Integer, nullable=True)  # Document image quality (1 to 100)
    quality_issues = Column(JSON, nullable=True)  # List of detected quality flags
    raw_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Document(document_id='{self.document_id}', "
            f"reference_id='{self.reference_id}', "
            f"status='{self.status}', category='{self.category}')>"
        )
