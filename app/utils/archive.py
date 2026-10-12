import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from typing import List
from fastapi import HTTPException, status
from app.config import settings

logger = logging.getLogger("archive_service")


@dataclass
class ExtractedDocument:
    document_id: str
    original_filename: str
    file_path: str


def sanitize_archive_filename(filename: str) -> str:
    """Sanitizes filename extracted from archive to prevent path traversal or special chars."""
    clean = os.path.basename(filename)
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean)
    return clean or "document"


def extract_zip_archive(
    zip_path: str,
    destination_dir: str = settings.UPLOAD_DIR,
    max_uncompressed_bytes: int = settings.MAX_ARCHIVE_UNCOMPRESSED_BYTES,
) -> List[ExtractedDocument]:
    """
    Safely unpacks a ZIP archive into the destination directory with enterprise security controls:
    - Zip Slip Directory Traversal protection
    - Zip Bomb memory/disk quota protection
    - Filtering of OS junk (__MACOSX, .DS_Store, Thumbs.db)
    - Filtering of unsupported non-document file types
    """
    if not os.path.exists(zip_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archive file not found: {zip_path}",
        )

    dest_root = os.path.abspath(destination_dir)
    os.makedirs(dest_root, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            # 1. Integrity and Zip Bomb audit
            total_uncompressed_size = 0
            valid_entries = []

            for info in archive.infolist():
                # Skip directories and zero-length metadata
                if info.is_dir():
                    continue

                # Skip macOS metadata or hidden files
                norm_name = info.filename.replace("\\", "/")
                if "__MACOSX" in norm_name or os.path.basename(norm_name).startswith("."):
                    continue

                ext = os.path.splitext(norm_name)[1].lower()
                if ext not in settings.DOCUMENT_EXTENSIONS:
                    logger.debug("Skipping non-document file in zip: %s (ext: %s)", norm_name, ext)
                    continue

                total_uncompressed_size += info.file_size
                if total_uncompressed_size > max_uncompressed_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"Total uncompressed ZIP size exceeds maximum limit of "
                            f"{max_uncompressed_bytes // (1024 * 1024)}MB."
                        ),
                    )

                if info.file_size > settings.MAX_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"File '{norm_name}' inside archive exceeds maximum allowed size of "
                            f"{settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
                        ),
                    )

                valid_entries.append(info)

            if not valid_entries:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"ZIP archive contains no valid supported document files. "
                        f"Supported formats: {', '.join(settings.DOCUMENT_EXTENSIONS)}"
                    ),
                )

            extracted_docs: List[ExtractedDocument] = []

            # 2. Extract validated entries safely
            for entry in valid_entries:
                raw_filename = os.path.basename(entry.filename)
                clean_name = sanitize_archive_filename(raw_filename)
                doc_id = f"doc_{uuid.uuid4().hex}"
                stored_name = f"{doc_id}_{clean_name}"
                target_path = os.path.abspath(os.path.join(dest_root, stored_name))

                # Zip Slip Protection: Ensure target path resolves inside dest_root
                if not target_path.startswith(dest_root + os.sep) and target_path != dest_root:
                    logger.error("Zip Slip path traversal attempt detected in entry: %s", entry.filename)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Malicious path detected inside ZIP archive.",
                    )

                # Write content safely
                with archive.open(entry) as source, open(target_path, "wb") as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)

                extracted_docs.append(
                    ExtractedDocument(
                        document_id=doc_id,
                        original_filename=clean_name,
                        file_path=target_path,
                    )
                )

            logger.info("Successfully extracted %d document(s) from ZIP archive %s", len(extracted_docs), zip_path)
            return extracted_docs

    except zipfile.BadZipFile as bze:
        logger.error("Corrupted or unreadable ZIP archive: %s", bze)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or corrupted ZIP archive: {bze}",
        )
