import re
import yaml
from pathlib import Path

POLICY_PATH = Path(__file__).parent / "policy.yaml"

def load_policy():
    with open(POLICY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def detect_prompt_injection(text: str, blocked_patterns):
    lower = text.lower()
    return any(p.lower() in lower for p in blocked_patterns)

def redact_pii(text: str, policy):
    if policy["pii"]["redact_phone"]:
        text = re.sub(r'(\+?\d[\d\s-]{7,}\d)', "[REDACTED_PHONE]", text)
    if policy["pii"]["redact_email"]:
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', "[REDACTED_EMAIL]", text)
    return text

def requires_human_review(severity_score: int, confidence: float, policy, keyword_hits=None):
    if severity_score >= policy["severity"]["human_review_threshold"]:
        return True
    if confidence < policy["severity"]["low_confidence_threshold"]:
        return True

    force_keywords = policy["severity"].get("force_review_keywords", [])
    if keyword_hits:
        for hazard in keyword_hits:
            if hazard in force_keywords:
                return True

    return False
