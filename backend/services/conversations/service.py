"""Report-specific conversations: ownership, saved turns and retries.

Every function returns None (or raises ConversationNotFound) when the report
or thread is missing or belongs to another user, so the API gives the same 404
either way. A question is saved before the model is asked, so a failure keeps
it in the history; a retry with the same ``request_id`` finds it and asks again
without saving a second copy.
"""

from typing import Optional

from sqlalchemy.exc import IntegrityError

from backend.database import repository
from backend.database.connection import session_scope
from backend.models.conversations import MAX_HISTORY_MESSAGES, QuestionRequest, QuestionResponse
from backend.services.conversations.answering import answer_question
from backend.services.conversations.grounding import build_grounding
from backend.services.suggestions import ai_wording
from backend.services.suggestions.evidence import load_evidence


class ConversationNotFound(LookupError):
    """The thread does not exist for this user and report."""


class RequestIdReused(ValueError):
    """A request_id was sent again with a different question."""


def _timestamp(value) -> str:
    return f"{value.isoformat()}Z"


def _message(record) -> dict:
    return {
        "message_id": record.id,
        "role": record.role,
        "content": record.content,
        "request_id": record.request_id,
        "created_at": _timestamp(record.created_at),
        "status": record.status,
        "sources": record.sources or [],
    }


def create_conversation(analysis_service, analysis_id: int, user_id: int) -> Optional[dict]:
    """Start an empty thread, or None when the user does not own the report."""
    with session_scope(analysis_service.engine) as session:
        if repository.get_analysis_for_user(session, analysis_id, user_id) is None:
            return None
        conversation = repository.create_conversation(
            session, analysis_id=analysis_id, user_id=user_id
        )
        return {
            "conversation_id": conversation.id,
            "analysis_id": analysis_id,
            "created_at": _timestamp(conversation.created_at),
            "message_count": 0,
            "first_question": None,
        }


def list_conversations(analysis_service, analysis_id: int, user_id: int) -> Optional[dict]:
    """The user's threads about one report, newest first."""
    with session_scope(analysis_service.engine) as session:
        if repository.get_analysis_for_user(session, analysis_id, user_id) is None:
            return None
        summaries = []
        for conversation in repository.list_conversations_for_user(session, analysis_id, user_id):
            messages = repository.list_conversation_messages(session, conversation.id)
            first = next((m.content for m in messages if m.role == "user"), None)
            summaries.append(
                {
                    "conversation_id": conversation.id,
                    "analysis_id": analysis_id,
                    "created_at": _timestamp(conversation.created_at),
                    "message_count": len(messages),
                    "first_question": first,
                }
            )
        return {"analysis_id": analysis_id, "conversations": summaries}


def get_history(
    analysis_service, analysis_id: int, conversation_id: int, user_id: int
) -> Optional[dict]:
    """Every saved message of one thread, oldest first."""
    with session_scope(analysis_service.engine) as session:
        conversation = repository.get_conversation_for_user(
            session, analysis_id, conversation_id, user_id
        )
        if conversation is None:
            return None
        return {
            "conversation_id": conversation.id,
            "analysis_id": analysis_id,
            "created_at": _timestamp(conversation.created_at),
            "messages": [
                _message(record)
                for record in repository.list_conversation_messages(session, conversation.id)
            ],
        }


def _save_question(analysis_service, analysis_id, user_id, request: QuestionRequest) -> tuple:
    """``(conversation_id, user_message)``, reusing the turn of a retry."""
    with session_scope(analysis_service.engine) as session:
        if request.conversation_id is not None:
            conversation = repository.get_conversation_for_user(
                session, analysis_id, request.conversation_id, user_id
            )
            if conversation is None:
                raise ConversationNotFound()
        else:
            conversation = repository.find_conversation_by_request(
                session, analysis_id, user_id, request.request_id
            ) or repository.create_conversation(session, analysis_id=analysis_id, user_id=user_id)
        existing = repository.get_conversation_message(
            session, conversation.id, "user", request.request_id
        )
        if existing is not None:
            if existing.content != request.question:
                raise RequestIdReused("This request_id was already used for a different question.")
            return conversation.id, _message(existing)
        saved = repository.add_conversation_message(
            session,
            conversation_id=conversation.id,
            role="user",
            request_id=request.request_id,
            content=request.question,
        )
        return conversation.id, _message(saved)


def _stored_answer(analysis_service, conversation_id: int, request_id: str) -> Optional[dict]:
    with session_scope(analysis_service.engine) as session:
        record = repository.get_conversation_message(
            session, conversation_id, "assistant", request_id
        )
        return None if record is None else _message(record)


def ask_question(
    analysis_service,
    analysis_id: int,
    user_id: int,
    request: QuestionRequest,
    complete: Optional[ai_wording.Complete] = None,
) -> Optional[dict]:
    """Answer one question about a report the user owns.

    Returns None when the user does not own the report. Raises
    ConversationNotFound for a thread that is not theirs or not this report's,
    and RequestIdReused when a request_id comes back with a different question.
    """
    with session_scope(analysis_service.engine) as session:
        report = repository.get_analysis_report_for_user(session, analysis_id, user_id)
    if report is None:
        return None

    conversation_id, user_message = _save_question(analysis_service, analysis_id, user_id, request)

    def response(status, assistant=None, reason=None, replayed=False) -> dict:
        return QuestionResponse(
            analysis_id=analysis_id,
            conversation_id=conversation_id,
            request_id=request.request_id,
            status=status,
            user_message=user_message,
            assistant_message=assistant,
            unavailable_reason=reason,
            replayed=replayed,
        ).model_dump(mode="json")

    stored = _stored_answer(analysis_service, conversation_id, request.request_id)
    if stored is not None:
        return response(stored["status"], stored, replayed=True)

    saved = analysis_service.list_comparisons(analysis_id, user_id)
    grounding = build_grounding(load_evidence(analysis_id, report, saved))
    with session_scope(analysis_service.engine) as session:
        history = [
            {"role": record.role, "content": record.content}
            for record in repository.list_conversation_messages(session, conversation_id)
            if record.id < user_message["message_id"]
        ][-MAX_HISTORY_MESSAGES:]

    reply, reason = answer_question(request.question, history, grounding, complete)
    if reply is None:
        return response("unavailable", reason=reason)

    sources = grounding.descriptors(reply["source_ids"])
    try:
        with session_scope(analysis_service.engine) as session:
            record = repository.add_conversation_message(
                session,
                conversation_id=conversation_id,
                role="assistant",
                request_id=request.request_id,
                content=reply["answer"],
                status=reply["status"],
                sources=sources,
            )
            assistant = _message(record)
    except IntegrityError:
        # A concurrent retry saved its answer first; return that one.
        assistant = _stored_answer(analysis_service, conversation_id, request.request_id)
        return response(assistant["status"], assistant, replayed=True)
    return response(reply["status"], assistant)
