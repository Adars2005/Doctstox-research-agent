from pathlib import Path
import mimetypes
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from config import MAX_UPLOAD_BYTES, UPLOAD_DIR
from db import add_file, get_conversation, get_file, get_file_raw, list_files, update_file
from services import gemini_file_search

router = APIRouter(prefix="/api")
SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".csv", ".json", ".doc", ".docx", ".xlsx",
    ".pptx", ".png", ".jpg", ".jpeg", ".html", ".htm",
}


def ensure_upload_size(total: int) -> None:
    if total > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 25 MB.")


def validate_upload_signature(filename: str, path: Path) -> None:
    extension = Path(filename).suffix.lower()
    with path.open("rb") as uploaded:
        prefix = uploaded.read(8192)
    signatures = {
        ".pdf": prefix.startswith(b"%PDF-"),
        ".png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": prefix.startswith(b"\xff\xd8\xff"),
        ".jpeg": prefix.startswith(b"\xff\xd8\xff"),
        ".doc": prefix.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        ".docx": prefix.startswith(b"PK\x03\x04"),
        ".xlsx": prefix.startswith(b"PK\x03\x04"),
        ".pptx": prefix.startswith(b"PK\x03\x04"),
    }
    valid = signatures.get(extension, b"\x00" not in prefix)
    if extension not in SUPPORTED_EXTENSIONS or not valid:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File extension does not match a supported document format.")


async def save_upload_stream(file: UploadFile, destination: Path) -> int:
    total = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(64 * 1024):
                total += len(chunk)
                ensure_upload_size(total)
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    return total


@router.get("/conversations/{conversation_id}/files")
def get_files(conversation_id: str) -> list[dict]:
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return list_files(conversation_id)


@router.post("/conversations/{conversation_id}/files")
async def upload_file(conversation_id: str, file: UploadFile = File(...)) -> dict:
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    filename = Path((file.filename or "upload").replace("\\", "/")).name[:180] or "upload.txt"
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="This file type is not supported.")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"{conversation_id}_{uuid.uuid4().hex}_{filename}"
    total = await save_upload_stream(file, dest)
    validate_upload_signature(filename, dest)

    try:
        record = add_file(
            conversation_id=conversation_id,
            filename=filename,
            mime_type=content_type,
            size_bytes=total,
            local_path=str(dest),
            status="indexing" if gemini_file_search.available() else "local_only",
            error=None
            if gemini_file_search.available()
            else "Saved locally. Add GEMINI_API_KEY to index this file for RAG.",
        )
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    if not gemini_file_search.available():
        return record

    raw = get_file_raw(record["id"])
    if not raw:
        raise HTTPException(status_code=500, detail="Uploaded file metadata could not be loaded.")
    try:
        document_name = gemini_file_search.upload_and_index(
            file_path=raw["local_path"],
            display_name=filename,
            conversation_id=conversation_id,
        )
        updated = update_file(
            record["id"],
            status="ready",
            gemini_document_name=document_name,
            error=None,
        )
        return updated or record
    except Exception as exc:
        updated = update_file(
            record["id"],
            status="error",
            error="File was saved, but Gemini File Search could not index it.",
        )
        return updated or {**record, "status": "error", "error": str(exc)}


@router.get("/files/{file_id}")
def file_status(file_id: str) -> dict:
    record = get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    return record
