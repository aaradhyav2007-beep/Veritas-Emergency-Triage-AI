import json
from datetime import datetime
from pathlib import Path

from agents.verification_agent import run_verification
from agents.triage_agent import run_triage
from agents.comms_agent import run_comms
from skills.evidence_engine import build_evidence
from guardrails.safety import (
    load_policy,
    detect_prompt_injection,
    requires_human_review,
    redact_pii,
)

AUDIT_PATH = Path("data/incidents.jsonl")
AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _write_audit(entry: dict):
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def process_incident(incident: dict):
    policy = load_policy()
    ts = datetime.utcnow().isoformat()

    if detect_prompt_injection(
        incident["report_text"],
        policy["security"]["blocked_patterns"],
    ):
        result = {
            "status": "blocked",
            "reason": "Potential prompt injection detected",
            "incident": incident,
        }
        _write_audit({"timestamp": ts, "incident": incident, "result": result})
        return result

    verification = run_verification(incident)
    triage = run_triage(incident, verification)
    evidence = build_evidence(incident, verification, triage)

    human_review = requires_human_review(
        severity_score=triage["final_score"],
        confidence=triage["confidence"],
        policy=policy,
        keyword_hits=triage["keyword_hits"],
    )

    message = run_comms(incident, triage, lang=incident.get("lang", "en"))
    message = redact_pii(message, policy)

    result = {
        "status": "needs_human_review" if human_review else "ready_to_dispatch",
        "verification": verification,
        "triage": triage,
        "evidence": evidence,
        "dispatch_message": message,
    }

    _write_audit({"timestamp": ts, "incident": incident, "result": result})
    return result
