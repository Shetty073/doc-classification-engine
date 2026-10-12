import io
import os
import zipfile
import pytest
from fastapi import HTTPException
from app.utils.archive import extract_zip_archive, sanitize_archive_filename


def create_sample_zip(entries: dict[str, bytes]) -> io.BytesIO:
    """Helper to construct in-memory zip archives for test cases."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in entries.items():
            zf.writestr(filename, data)
    buf.seek(0)
    return buf


def test_sanitize_archive_filename():
    assert sanitize_archive_filename("folder/sub/doc1.pdf") == "doc1.pdf"
    assert sanitize_archive_filename("../../etc/passwd.png") == "passwd.png"
    assert sanitize_archive_filename("document @#$ (1).pdf") == "document______1_.pdf"


def test_extract_valid_zip_archive(tmp_path):
    zip_entries = {
        "pan_card.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy_png",
        "nested/subfolder/bank_statement.pdf": b"%PDF-1.4 sample bank statement dummy",
        "readme.txt": b"This is a text file that should be skipped",
        ".DS_Store": b"junk macos metadata",
        "__MACOSX/._pan_card.png": b"junk macos shadow file",
    }
    zip_bytes = create_sample_zip(zip_entries)
    zip_file = tmp_path / "test_dossier.zip"
    zip_file.write_bytes(zip_bytes.getvalue())

    dest_dir = tmp_path / "extracted"
    extracted_docs = extract_zip_archive(str(zip_file), destination_dir=str(dest_dir))

    assert len(extracted_docs) == 2
    filenames = [d.original_filename for d in extracted_docs]
    assert "pan_card.png" in filenames
    assert "bank_statement.pdf" in filenames

    for doc in extracted_docs:
        assert os.path.exists(doc.file_path)
        assert doc.document_id.startswith("doc_")


def test_extract_zip_with_no_valid_docs(tmp_path):
    zip_entries = {
        "notes.txt": b"Hello world",
        "script.sh": b"#!/bin/bash echo hi",
    }
    zip_bytes = create_sample_zip(zip_entries)
    zip_file = tmp_path / "no_docs.zip"
    zip_file.write_bytes(zip_bytes.getvalue())

    with pytest.raises(HTTPException) as exc_info:
        extract_zip_archive(str(zip_file), destination_dir=str(tmp_path))
    assert exc_info.value.status_code == 400
    assert "no valid supported document files" in exc_info.value.detail


def test_zip_bomb_prevention(tmp_path):
    # Create an entry with uncompressed size exceeding quota
    large_data = b"0" * (1024 * 1024 * 5)  # 5MB
    zip_bytes = create_sample_zip({"huge.pdf": large_data})
    zip_file = tmp_path / "huge.zip"
    zip_file.write_bytes(zip_bytes.getvalue())

    # Set quota lower than 5MB
    with pytest.raises(HTTPException) as exc_info:
        extract_zip_archive(str(zip_file), destination_dir=str(tmp_path), max_uncompressed_bytes=1024 * 1024 * 2)
    assert exc_info.value.status_code == 413
    assert "exceeds maximum limit" in exc_info.value.detail


def test_zip_slip_prevention(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Malicious traversal path
        info = zipfile.ZipInfo("../../../evil.pdf")
        zf.writestr(info, b"%PDF-1.4 evil")
    buf.seek(0)

    zip_file = tmp_path / "slip.zip"
    zip_file.write_bytes(buf.getvalue())

    dest_dir = tmp_path / "safe_dir"
    # Even with zip slip in entry, sanitize_archive_filename uses os.path.basename
    # and extract_zip_archive enforces target_path.startswith(dest_root)
    extracted = extract_zip_archive(str(zip_file), destination_dir=str(dest_dir))
    assert len(extracted) == 1
    # Ensured path is safe within dest_dir
    assert os.path.dirname(extracted[0].file_path) == str(dest_dir)
