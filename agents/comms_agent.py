from skills.translate_dispatch import build_dispatch_message

def run_comms(incident: dict, triage_result: dict, lang="en"):
    return build_dispatch_message(
        incident=incident,
        severity=triage_result["tier"],
        resources=triage_result["resources"],
        lang=lang
    )
