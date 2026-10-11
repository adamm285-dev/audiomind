"""
server.py - Standalone FastAPI Server for Antigravity Cloud Relay.
"""
import os
from fastapi import FastAPI
from contextlib import asynccontextmanager

from models import init_db
from agent_dispatch_router import router as agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enforce minimum secret length on server startup (fail closed)
    secret = os.environ.get("RELAY_AUTH_SECRET", "").strip()
    if not secret or len(secret) < 32:
        raise RuntimeError(
            "Relay server refused to start: RELAY_AUTH_SECRET environment variable must be set and at least 32 characters long."
        )
    # Initialize SQLite database schema
    init_db()
    yield


app = FastAPI(
    title="AudioMind Cloud Relay",
    version="1.0.0",
    description="Relay between mobile Google Assistant / Gemini voice commands and desktop Antigravity IDE",
    lifespan=lifespan
)

app.include_router(agent_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "anti-voice-relay"}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("RELAY_HOST", "127.0.0.1")
    port = int(os.environ.get("RELAY_PORT", "8000"))
    reload = os.environ.get("RELAY_RELOAD", "false").lower() == "true"
    uvicorn.run("server:app", host=host, port=port, reload=reload)
