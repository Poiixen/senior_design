"""Request and response models for report follow-up questions.

Endpoints (all under an existing authenticated session; a report or thread
the user does not own is a 404):

    POST /api/reports/{analysis_id}/questions
    POST /api/reports/{analysis_id}/conversations
    GET  /api/reports/{analysis_id}/conversations
    GET  /api/reports/{analysis_id}/conversations/{conversation_id}

Sources, statuses and ids are set by the backend. The model only chooses
which of the backend-provided sources support its answer.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

MAX_QUESTION_CHARS = 1000
MAX_ANSWER_CHARS = 2000
MAX_REQUEST_ID_CHARS = 64
MAX_HISTORY_MESSAGES = 6

SourceKind = Literal["finding", "comparison", "report"]
AnswerStatus = Literal["answered", "insufficient_evidence"]


class QuestionRequest(BaseModel):
    """One follow-up question.

    ``request_id`` is chosen by the client and reused when it retries the same
    question, so a retry never saves the turn twice. ``conversation_id`` is
    optional: without it a new thread is started.
    """

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    request_id: str = Field(min_length=1, max_length=MAX_REQUEST_ID_CHARS, pattern=r"^[A-Za-z0-9_.:-]+$")
    conversation_id: Optional[int] = None


class Source(BaseModel):
    """A saved result an answer relied on."""

    source_id: str
    kind: SourceKind
    label: str
    finding_id: Optional[str] = None
    comparison_id: Optional[int] = None
    method: Optional[str] = None


class Message(BaseModel):
    message_id: int
    role: Literal["user", "assistant"]
    content: str
    request_id: str
    created_at: str
    # Assistant messages only.
    status: Optional[AnswerStatus] = None
    sources: list[Source] = Field(default_factory=list)


class QuestionResponse(BaseModel):
    """``status`` is "unavailable" when no answer could be produced.

    The question is still saved, and retrying with the same ``request_id``
    asks again without adding a second copy of it.
    """

    analysis_id: int
    conversation_id: int
    request_id: str
    status: Literal["answered", "insufficient_evidence", "unavailable"]
    user_message: Message
    assistant_message: Optional[Message] = None
    # Set when status is "unavailable".
    unavailable_reason: Optional[str] = None
    # True when the stored answer for this request_id was returned unchanged.
    replayed: bool = False


class ConversationSummary(BaseModel):
    conversation_id: int
    analysis_id: int
    created_at: str
    message_count: int
    first_question: Optional[str] = None


class ConversationList(BaseModel):
    analysis_id: int
    conversations: list[ConversationSummary]


class ConversationHistory(BaseModel):
    conversation_id: int
    analysis_id: int
    created_at: str
    messages: list[Message]
