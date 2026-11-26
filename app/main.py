"""Research API. No real-game controls or social publishing."""
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .personality import DISCLOSURE, comment
from .simulation import run_episode

app = FastAPI(title="APEX Research API", version="0.1.0")

class EpisodeRequest(BaseModel):
    seed: int = Field(default=7, ge=0, le=1000000)

class CommentRequest(BaseModel):
    event: str
    context: str = Field(default="", max_length=256)

def authorize(key: str | None):
    expected = os.environ.get("APEX_API_KEY", "")
    if not expected or not key or key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/health")
def health():
    return {"status": "ok", "service": "apex", "mode": "simulation"}

@app.get("/identity")
def identity(x_apex_key: str | None = Header(default=None)):
    authorize(x_apex_key)
    return {"name": "APEX", "disclosure": DISCLOSURE, "autonomous_game": "simulated"}

@app.post("/episodes")
def episode(request: EpisodeRequest, x_apex_key: str | None = Header(default=None)):
    authorize(x_apex_key)
    return run_episode(request.seed)

@app.post("/commentary")
def commentary(request: CommentRequest, x_apex_key: str | None = Header(default=None)):
    authorize(x_apex_key)
    try:
        return comment(request.event, request.context)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc