from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import logging

from db import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    list_files,
    list_files_raw,
    list_messages,
)
from services.orchestrator import run_turn
from config import UPLOAD_DIR
from services import gemini_file_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class CreateConversationBody(BaseModel):
    title: str | None = None


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=12000)


@router.get("/conversations")
def get_conversations() -> list[dict]:
    return list_conversations()


@router.post("/conversations")
def post_conversation(body: CreateConversationBody | None = None) -> dict:
    title = (body.title if body else None) or "New research"
    return create_conversation(title=title)


@router.get("/conversations/{conversation_id}")
def get_one_conversation(conversation_id: str) -> dict:
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        **conversation,
        "messages": list_messages(conversation_id),
        "files": list_files(conversation_id),
    }


@router.delete("/conversations/{conversation_id}")
def remove_conversation(conversation_id: str) -> dict:
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    files = list_files_raw(conversation_id)
    for item in files:
        document_name = item.get("gemini_document_name")
        if document_name:
            try:
                gemini_file_search.delete_document(document_name)
            except gemini_file_search.GeminiError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="An indexed document could not be deleted. The conversation was kept so deletion can be retried.",
                ) from exc

    upload_root = UPLOAD_DIR.resolve()
    for item in files:
        local_path = item.get("local_path")
        if not local_path:
            continue
        path = Path(local_path).resolve()
        if not path.is_relative_to(upload_root):
            raise HTTPException(
                status_code=500,
                detail="An uploaded file is outside the managed upload directory. The conversation was kept for review.",
            )
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.exception("Could not remove uploaded file during conversation deletion")
            raise HTTPException(
                status_code=500,
                detail="A local upload could not be deleted. The conversation was kept so deletion can be retried.",
            ) from exc

    if not delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}


@router.post("/conversations/{conversation_id}/messages")
def post_message(conversation_id: str, body: MessageBody) -> dict:
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    question = body.content.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        return run_turn(conversation_id, question)
    except Exception:
        raise HTTPException(status_code=502, detail="The research agent could not complete this turn.")
