"""Secure file storage and quarantine management for multi-tenant ingestion."""

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException, UploadFile, status

# Default maximum upload size: 100 MB
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MB chunk


def sanitize_filename(filename: str) -> str:
    """Sanitize original filename to strip directory traversal and unsafe characters."""
    # Strip path separators
    clean_name = os.path.basename(filename)
    # Remove null bytes, control characters, and keep safe characters
    clean_name = re.sub(r"[^\w\.\-\s]", "_", clean_name).strip()
    if not clean_name or clean_name.startswith("."):
        clean_name = f"dataset_{uuid.uuid4().hex[:8]}.dat"
    return clean_name


def get_workspace_storage_dir(workspace_id: str, base_dir: str = "data") -> Path:
    """Resolve and create isolated quarantine storage path for a workspace."""
    target_dir = Path(base_dir) / "workspaces" / workspace_id / "raw"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


async def stream_save_upload_file(
    upload_file: UploadFile,
    workspace_id: str,
    max_size_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    base_dir: str = "data",
) -> Tuple[Path, str, int, str]:
    """
    Stream upload file in chunks to prevent unbounded memory spikes.
    Calculates SHA-256 fingerprint concurrently and enforces file size boundaries.
    
    Returns:
        (saved_path, clean_filename, total_bytes_written, sha256_hash)
    """
    clean_name = sanitize_filename(upload_file.filename or "upload.dat")
    storage_dir = get_workspace_storage_dir(workspace_id, base_dir=base_dir)

    unique_prefix = uuid.uuid4().hex[:12]
    target_file_path = storage_dir / f"{unique_prefix}_{clean_name}"

    hasher = hashlib.sha256()
    bytes_written = 0

    try:
        with open(target_file_path, "wb") as destination:
            while True:
                chunk = await upload_file.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break

                bytes_written += len(chunk)
                if bytes_written > max_size_bytes:
                    destination.close()
                    if target_file_path.exists():
                        target_file_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed upload size of {max_size_bytes / (1024 * 1024):.1f} MB.",
                    )

                hasher.update(chunk)
                destination.write(chunk)

    except HTTPException:
        raise
    except Exception as e:
        if target_file_path.exists():
            target_file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving file to workspace storage: {str(e)}",
        )

    return target_file_path, clean_name, bytes_written, hasher.hexdigest()
