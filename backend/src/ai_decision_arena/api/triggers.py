"""Triggers over HTTP (triggers.py):

    GET  /api/triggers                               → the trigger table (event, condition, action, where)
    POST /api/triggers/idle-previews                 → stop previews idle for PREVIEW_IDLE_MINUTES now
    POST /api/triggers/idle-previews?idle_minutes=0  → stop every running preview now
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ai_decision_arena.triggers import TRIGGERS, run_idle_previews

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


class TriggerTable(BaseModel):
    triggers: list[dict[str, str]]


class IdlePreviewResult(BaseModel):
    stopped: list[str]             # thread ids whose preview was stopped


@router.get("", response_model=TriggerTable)
def list_triggers():
    return TriggerTable(triggers=TRIGGERS)


@router.post("/idle-previews", response_model=IdlePreviewResult)
def trigger_idle_previews(request: Request, idle_minutes: float | None = None):
    return IdlePreviewResult(stopped=run_idle_previews(request.app.state.processes, idle_minutes))
