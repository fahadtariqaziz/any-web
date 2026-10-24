"""Patient chat endpoints (the ChatGPT-style page of the frontend).

A chat IS a quick session: POST /api/decisions {"mode": "quick"} starts its onboarding (intake → questions →
the agents → report + short summary), and the usual GET / resume endpoints drive it. Once the report exists:

    GET  /api/chats/{id}             → transcript: first message, answered questions, summary, chat messages
    POST /api/chats/{id}/messages    → {"content"}; the reply STREAMS back as plain text (read it chunk by chunk)

The user's message is saved before the reply starts, the reply once it is complete. If the reply fails half
way, the partial text ends with a note and is not saved (the user can simply ask again).
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ai_decision_arena.api.errors import ApiError
from ai_decision_arena.api.runner import graph_config
from ai_decision_arena.api.schemas import ChatMessageRequest, ChatMessageView, ChatTranscript, ClarificationTurn
from ai_decision_arena.chat import stream_reply
from ai_decision_arena.db.repository import add_chat_message, list_chat_messages

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chat"])

SKIPPED = "(skipped by user)"


def _values(request: Request, thread_id: str) -> dict:
    values = request.app.state.graph.get_state(graph_config(thread_id)).values
    if not values and not request.app.state.runner.is_running(thread_id):
        raise ApiError(404, "not_found", f"No chat with id {thread_id}.")
    return values or {}


def _messages(thread_id: str) -> list[ChatMessageView]:
    try:
        rows = list_chat_messages(thread_id)
    except Exception as exc:                        # noqa: BLE001 - shown as a clear 503 instead of a 500
        log.exception("could not read chat messages")
        raise ApiError(503, "database_unavailable", f"Could not read the chat: {type(exc).__name__}.") from exc
    return [ChatMessageView(role=r.role, content=r.content, created_at=r.created_at.isoformat(timespec="seconds"))
            for r in rows]


@router.get("/{thread_id}", response_model=ChatTranscript)
def get_chat(thread_id: str, request: Request):
    values = _values(request, thread_id)
    ready = bool(values.get("final_report"))
    return ChatTranscript(
        thread_id=thread_id,
        mode=values.get("mode") or "full",
        question=values.get("question"),
        condition_name=values.get("condition_name"),
        clarifications=[ClarificationTurn(question=q, answer=a) for q, a in values.get("clarification_answers", {}).items()],
        onboarding_summary=values.get("onboarding_summary"),
        ready=ready,
        messages=_messages(thread_id) if ready else [],
    )


@router.post("/{thread_id}/messages")
def send_message(thread_id: str, body: ChatMessageRequest, request: Request):
    values = _values(request, thread_id)
    if not values.get("final_report"):
        raise ApiError(409, "onboarding_not_finished", "I'm still getting to know your situation; one moment please.")
    history = [{"role": m.role, "content": m.content} for m in _messages(thread_id)]
    try:
        add_chat_message(thread_id, "user", body.content)
    except Exception as exc:                        # noqa: BLE001
        log.exception("could not save chat message")
        raise ApiError(503, "database_unavailable", f"Could not save your message: {type(exc).__name__}.") from exc

    def generate():
        parts: list[str] = []
        try:
            for piece in stream_reply(thread_id, values, history, body.content):
                parts.append(piece)
                yield piece
        except Exception:                           # noqa: BLE001 - the status code is already sent: say it in the text
            log.exception("chat reply failed for %s", thread_id)
            yield "\n\n_(Sorry, my reply was interrupted. Please send your message again.)_"
            return
        reply = "".join(parts).strip()
        if reply:
            try:
                add_chat_message(thread_id, "assistant", reply)
            except Exception:                       # noqa: BLE001 - the user already has the text on screen
                log.exception("could not save chat reply for %s", thread_id)

    # X-Accel-Buffering: tells proxies (nginx) not to hold the stream back; harmless locally.
    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
