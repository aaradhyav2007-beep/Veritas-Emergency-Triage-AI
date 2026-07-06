"""
Tests for skills/ai_reasoning.py.

Only the "no API key configured" path is tested here -- it's the one
branch that's fully deterministic without a network call. The actual
Gemini call (success/failure) is exercised manually against the running
app, same as the rest of this codebase's network-touching code.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.ai_reasoning import assess_with_ai


INCIDENT = {"report_text": "Fire near the market.", "location": "Market Square"}
VERIFICATION = {"location_verified": True}


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    result = assess_with_ai(INCIDENT, VERIFICATION, hazard="fire")

    assert result["ai_available"] is False
    assert result["ai_score"] is None


def test_missing_key_reports_specific_error(monkeypatch):
    """This is what surfaces in the 'AI Reasoning Agent' expander in the
    UI -- it should say *why* the pass didn't run, not just that it
    didn't."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    result = assess_with_ai(INCIDENT, VERIFICATION, hazard="fire")

    assert result["ai_error"] == "GOOGLE_API_KEY not set"


def test_missing_key_never_raises():
    import os
    old = os.environ.pop("GOOGLE_API_KEY", None)
    try:
        result = assess_with_ai(INCIDENT, VERIFICATION, hazard="fire")
        assert isinstance(result, dict)
    finally:
        if old is not None:
            os.environ["GOOGLE_API_KEY"] = old
