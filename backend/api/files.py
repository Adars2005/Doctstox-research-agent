from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from config import ALLOWED_UPLOAD_TYPES, MAX_UPLOAD_BYTES, UPLOAD_DIR
from db import add_file, get_conversation, get_file, get_file_raw, list_files, update_file
from services import gemini_file_search

router = APIRouter(prefix="/api")


@router.get("/conversations/{conversation_id}/files")
def get_files(conversation_id: str) -> list[dict]:
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return list_files(conversation_id)


@router.post("/conversations/{conversation_id}/files")
async def upload_file(conversation_id: str, file: UploadFile = File(...)) -> dict:
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    filename = Path(file.filename or "upload").name
    content_type = file.content_type or "application/octet-stream"
    if content_type.startswith("audio/") or content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Audio and video files are not supported for File Search.")
    if content_type not in ALLOWED_UPLOAD_TYPES and not filename.lower().endswith(
        (".txt", ".md", ".pdf", ".csv", ".json", ".docx", ".png", ".jpg", ".jpeg")
    ):
        raise HTTPException(status_code=400, detail="This file type is not supported.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is larger than 25 MB.")

    dest = UPLOAD_DIR / f"{conversation_id}_{filename}"
    dest.write_bytes(data)

    record = add_file(
        conversation_id=conversation_id,
        filename=filename,
        mime_type=content_type,
        size_bytes=len(data),
        local_path=str(dest),
        status="indexing" if gemini_file_search.available() else "local_only",
        error=None
        if gemini_file_search.available()
        else "Saved locally. Add GEMINI_API_KEY to index this file for RAG.",
    )

    if not gemini_file_search.available():
        return record

    raw = get_file_raw(record["id"])
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
