from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chats import router as chats_router
from api.files import router as files_router
from api.voice import router as voice_router
from config import key_status
from db import init_db

app = FastAPI(
    title="Docstox-research agent",
    description="Evidence-driven AI equity research agent",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chats_router)
app.include_router(files_router)
app.include_router(voice_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    keys = key_status()
    return {
        "status": "ok",
        "service": "docstox-research-agent",
        "phase": "chat",
        "providers": keys,
    }
