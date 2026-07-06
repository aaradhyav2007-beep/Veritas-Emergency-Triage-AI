import json
from datetime import datetime
from pathlib import Path

AUDIT_PATH = Path("data/incidents.jsonl")

def append_review_action(incident: dict, triage: dict, action: str, reviewer: str = "dispatcher_1", note: str = ""):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": "human_review_action",
        "reviewer": reviewer,
        "action": action,  # approve | hold | reject
        "note": note,
        "incident": incident,
        "triage": triage
    }
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry