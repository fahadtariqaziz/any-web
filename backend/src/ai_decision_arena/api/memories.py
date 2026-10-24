"""Long-term memory endpoints: see and delete what the agents remember about this browser's patient.

    GET    /api/memories    → the remembered facts (X-User-Id header)
    DELETE /api/memories    → forget everything ("forget me"; a guardrail: the patient controls their memory)
"""

from typing import Annotated

from fastapi import APIRouter, Header

from ai_decision_arena import memory
from ai_decision_arena.api.errors import ApiError
from ai_decision_arena.api.schemas import MemoryList
from ai_decision_arena.db.repository import list_memories

router = APIRouter(prefix="/api/memories", tags=["memory"])
PatientHeader = Annotated[str | None, Header(description="Anonymous browser id.")]


def _patient(x_user_id: str | None) -> str:
    user_id = memory.valid_user_id(x_user_id)
    if not user_id:
        raise ApiError(400, "missing_patient_id", "Send the X-User-Id header (the browser's anonymous id).")
    return user_id


@router.get("", response_model=MemoryList)
def get_memories(x_user_id: PatientHeader = None):
    user_id = _patient(x_user_id)
    rows = list_memories(user_id, limit=200)
    return MemoryList(facts=[{"fact": r.fact, "source": r.source, "created_at": r.created_at.isoformat(timespec="seconds")}
                             for r in rows])


@router.delete("", response_model=MemoryList)
def forget_memories(x_user_id: PatientHeader = None):
    memory.forget(_patient(x_user_id))
    return MemoryList(facts=[])
