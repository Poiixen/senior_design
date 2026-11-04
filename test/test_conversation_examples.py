"""The committed conversation samples still match the response models."""

import json
import pathlib

import pytest

from backend.models.conversations import (
    ConversationHistory,
    ConversationList,
    ConversationSummary,
    QuestionRequest,
    QuestionResponse,
)

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "docs" / "examples" / "conversations"
MODELS = {
    "unavailable": QuestionResponse,
    "answered_after_retry": QuestionResponse,
    "replayed": QuestionResponse,
    "insufficient_evidence": QuestionResponse,
    "history": ConversationHistory,
    "conversation_list": ConversationList,
    "conversation_created": ConversationSummary,
}


@pytest.mark.parametrize("name", sorted(MODELS))
def test_sample_matches_its_model(name):
    sample = json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))

    MODELS[name](**sample["response"])
    if MODELS[name] is QuestionResponse:
        QuestionRequest(**sample["request"])


def test_every_sample_file_is_checked():
    assert {path.stem for path in EXAMPLES.glob("*.json")} == set(MODELS)
