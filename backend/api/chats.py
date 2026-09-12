from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    list_files,
    list_messages,
)
from services.orchestrator import run_turn

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
