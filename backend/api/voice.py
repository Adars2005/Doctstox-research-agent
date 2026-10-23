from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from config import MAX_AUDIO_BYTES
from services import groq_client

router = APIRouter(prefix="/api")


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/voice/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    data = await file.read(MAX_AUDIO_BYTES + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="No audio received.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio is larger than 25 MB.")
    try:
        text = groq_client.transcribe_audio(
            filename=file.filename or "speech.webm",
            content=data,
            content_type=file.content_type,
        )
    except groq_client.GroqError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"text": text}


@router.post("/voice/speak")
def speak(body: SpeakBody) -> Response:
    try:
        audio = groq_client.speak(body.text)
    except groq_client.GroqError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/wav")
