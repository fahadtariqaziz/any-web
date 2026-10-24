"""Manual trigger endpoint (the same job also runs on a schedule, see triggers.py).

    POST /api/triggers/check-ins                       → check-ins for chats quiet for CHECK_IN_QUIET_HOURS
    POST /api/triggers/check-ins?quiet_hours=0         → every finished chat whose last message isn't a check-in
    POST /api/triggers/check-ins?thread_id=<id>        → one chat, now
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ai_decision_arena.triggers import run_check_ins

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


class CheckInResult(BaseModel):
    checked_in: list[str]          # thread ids that got a check-in message


@router.post("/check-ins", response_model=CheckInResult)
def trigger_check_ins(request: Request, quiet_hours: float | None = None, thread_id: str | None = None):
    return CheckInResult(checked_in=run_check_ins(request.app.state.graph, quiet_hours=quiet_hours, thread_id=thread_id))
