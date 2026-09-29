"""Local-disk file storage behind a small interface (S3-compatible swap later).

Files are stored under settings.storage_dir/<subdir>/<uuid>_<safe_name> so user
input never controls the final path.
"""
import re
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".xls", ".xlsx",
    ".csv", ".txt",
    # Onboarding asset uploads: sales decks, brand guidelines, project videos and
    # drone footage (§16 of AI_Developer_Onboarding_Form.md).
    ".ppt", ".pptx", ".mp4", ".mov", ".webm",
}

# Deliberately absent: .svg and .html. Both execute script when a browser renders
# them inline, and every download path here is authenticated but same-origin.


def _safe_name(filename: str) -> str:
    name = Path(filename or "file").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]
    return name or "file"


def save_file(subdir: str, filename: str, content: bytes) -> dict:
    settings = get_settings()
    if not content:
        # A browser that fails mid-upload sends an empty part; storing it creates a
        # 0-byte "document" that looks uploaded and downloads as nothing.
        raise AppError("File is empty", code="empty_file")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(
            f"File exceeds {settings.max_upload_mb} MB limit", code="file_too_large"
        )
    safe = _safe_name(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(
            f"File type '{ext or 'unknown'}' not allowed", code="unsupported_file_type"
        )
    stored_name = f"{uuid.uuid4().hex}_{safe}"
    target_dir = settings.storage_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / stored_name
    path.write_bytes(content)
    return {"stored_path": f"{subdir}/{stored_name}", "filename": safe, "size": len(content)}


def read_file(stored_path: str) -> bytes:
    settings = get_settings()
    base = settings.storage_dir.resolve()
    path = (settings.storage_dir / stored_path).resolve()
    if not str(path).startswith(str(base)):  # path traversal guard
        raise AppError("Invalid file path", code="invalid_path")
    if not path.exists():
        raise AppError("File not found", code="not_found", status_code=404)
    return path.read_bytes()
