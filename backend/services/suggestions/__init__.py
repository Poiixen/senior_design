"""Evidence-based report suggestions (Ticket #47)."""

from backend.services.suggestions.evidence import InvalidComparisonSelection
from backend.services.suggestions.service import generate_suggestions

__all__ = ["InvalidComparisonSelection", "generate_suggestions"]
