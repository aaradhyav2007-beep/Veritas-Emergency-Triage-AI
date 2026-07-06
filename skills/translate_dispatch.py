"""
Translate & Dispatch Skill

Builds the final dispatch message for an incident and, if a non-English
language was requested, translates it via Gemini (the same
google-genai / GOOGLE_API_KEY path used by skills/ai_reasoning.py).

Fails CLOSED like the rest of the evidence pipeline: if GOOGLE_API_KEY
is missing or the translation call fails for any reason, this never
silently returns English text mislabeled as the target language --
it clearly flags that translation was unavailable and falls back to
English so a dispatcher never misreads a language-tagged message as
correctly translated when it isn't.
"""

import logging
import os

from google import genai

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
}


def _translate(text: str, lang: str) -> tuple:
    """
    Translate `text` into the language identified by `lang` (e.g. "hi",
    "es"). Returns (translated_text, error) -- translated_text is None
    on any failure, with `error` describing why.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None, "GOOGLE_API_KEY not set"

    target_language = LANGUAGE_NAMES.get(lang, lang)

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Translate the following emergency dispatch alert into "
            f"{target_language}. Preserve all place names, unit names, "
            f"and numbers exactly as given. Respond with ONLY the "
            f"translated text -- no explanations, no quotes, no markdown.\n\n"
            f"{text}"
        )

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        translated = (response.text or "").strip()
        if not translated:
            return None, "empty response from model"

        return translated, None

    except Exception as e:
        logger.warning("Dispatch translation to '%s' failed: %s: %s", lang, type(e).__name__, e)
        return None, f"{type(e).__name__}: {e}"


def build_dispatch_message(incident, severity, resources, lang="en", max_report_chars=160):
    report = incident["report_text"].strip().rstrip(". ")
    if len(report) > max_report_chars:
        report = report[:max_report_chars].rstrip() + "..."

    base = (
        f"ALERT [{severity}] at {incident['location']}. "
        f"Issue: {report}. "
        f"Recommended response: {', '.join(resources)}."
    )

    if lang == "en":
        return base

    translated, error = _translate(base, lang)
    if translated is not None:
        return translated

    # Fail closed: never present untranslated English as if it were
    # translated -- label it clearly instead.
    language_name = LANGUAGE_NAMES.get(lang, lang)
    return f"[Translation to {language_name} unavailable -- showing English] {base}"
