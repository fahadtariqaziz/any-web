"""Long-term memory endpoints: see and delete what the agents remember about this browser's patient.

    GET    /api/memories    → the remembered facts (X-Patient-Id header)
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


def _patient(x_patient_id: str | None) -> str:
    patient_id = memory.valid_patient_id(x_patient_id)
    if not patient_id:
        raise ApiError(400, "missing_patient_id", "Send the X-Patient-Id header (the browser's anonymous id).")
    return patient_id


@router.get("", response_model=MemoryList)
def get_memories(x_patient_id: PatientHeader = None):
    patient_id = _patient(x_patient_id)
    rows = list_memories(patient_id, limit=200)
    return MemoryList(facts=[{"fact": r.fact, "source": r.source, "created_at": r.created_at.isoformat(timespec="seconds")}
                             for r in rows])


@router.delete("", response_model=MemoryList)
def forget_memories(x_patient_id: PatientHeader = None):
    memory.forget(_patient(x_patient_id))
    return MemoryList(facts=[])
