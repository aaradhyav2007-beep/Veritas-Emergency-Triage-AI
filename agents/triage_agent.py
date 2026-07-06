from skills.severity_score import score_from_text, combine_scores, severity_tier
from skills.resource_mapper import map_resources


def run_triage(incident: dict, verification: dict):
    # Rule-based severity
    rule_score, hits = score_from_text(incident["report_text"])
    
    # Combine all external verification boosts: weather, water level, and seismic
    weather_boost = verification.get("weather_risk_boost", 0)
    water_boost = verification.get("water_level_risk_boost", 0)
    seismic_boost = verification.get("seismic_risk_boost", 0)
    
    # Apply all verification boosts to the rule score
    total_verification_boost = weather_boost + water_boost + seismic_boost
    rule_score = min(100, rule_score + total_verification_boost)

    # AI reasoning score from Gemini (skills/ai_reasoning.py). ai_score is
    # None when the AI pass was unavailable (no API key / call failed) --
    # fall back to the rule score so combine_scores never silently degrades
    # to "rule score weighted twice".
    ai_score = verification.get("ai_score")
    llm_score = ai_score if ai_score is not None else rule_score

    # Corroboration boost: multiple independent reports of the same hazard
    # nearby and recently is folded in alongside the external verification boosts,
    # since both are "external evidence that isn't just this one report's text".
    corroboration_boost = verification.get("corroboration_boost", 0)
    combined_external_boost = min(20, total_verification_boost + corroboration_boost)

    final_score = combine_scores(
        rule_score,
        llm_score,
        combined_external_boost
    )

    # If Gemini determined the report explicitly negates/retracts the
    # hazard ("fire is out", "false alarm"), the keyword scorer can't see
    # that distinction -- trust the AI reasoning pass and cap the score so
    # a retracted incident doesn't get dispatched as if it were active.
    if verification.get("negated"):
        final_score = min(final_score, 20)

    tier = severity_tier(final_score)

    # -------------------------
    # Confidence Assessment
    # -------------------------
    confidence_score = 0

    # Hazard detected
    if hits:
        confidence_score += 30

    # Verified location
    if verification.get("location_verified"):
        confidence_score += 25

    # Weather successfully retrieved
    if verification.get("live_weather"):
        confidence_score += 20

    # Water level data successfully retrieved
    if verification.get("live_water_data"):
        confidence_score += 15

    # Seismic data successfully retrieved
    if verification.get("live_seismic_data"):
        confidence_score += 15

    # Sensor confidence
    sensor_value = incident.get("sensor_value", 0)

    if sensor_value >= 70:
        confidence_score += 15
    elif sensor_value >= 40:
        confidence_score += 10
    else:
        confidence_score += 5

    # Report detail
    if len(incident["report_text"].split()) >= 8:
        confidence_score += 10

    # AI reasoning pass: only add confidence if it actually ran, and only
    # in proportion to how confident Gemini itself was. If it contradicted
    # the report against the collected evidence, that's a red flag and
    # should pull confidence down. If it didn't run at all, that's a missing
    # evidence source and should also pull confidence down -- otherwise a
    # report can hit 100% confidence on the other four signals alone.
    if verification.get("ai_available"):
        confidence_score += verification.get("ai_confidence", 0) * 10
        if verification.get("contradicts_evidence"):
            confidence_score -= 15
    else:
        confidence_score -= 15

    # Corroboration: independent reports nearby/recently is strong evidence
    # the system can actually point a human reviewer to (the matches list),
    # not just a confidence number.
    corroboration_count = verification.get("corroboration_count", 0)
    if corroboration_count > 0:
        confidence_score += min(15, corroboration_count * 8)

    confidence_score = max(0, confidence_score)
    confidence = min(confidence_score / 100, 1.0)

    return {
        "rule_score": rule_score,
        "ai_score": ai_score,
        "final_score": final_score,
        "tier": tier,
        "confidence": confidence,
        "keyword_hits": hits,
        "resources": map_resources(tier, hits),
        "ai_available": verification.get("ai_available", False),
        "ai_rationale": verification.get("rationale", ""),
        "ai_negated": verification.get("negated", False),
        "ai_contradicts_evidence": verification.get("contradicts_evidence", False),
        "ai_error": verification.get("ai_error"),
        "corroboration_count": corroboration_count,
        "corroboration_matches": verification.get("matches", []),
        "water_level_risk_boost": water_boost,
        "water_level_severity": verification.get("water_level_severity", "unknown"),
        "seismic_risk_boost": seismic_boost,
        "seismic_severity": verification.get("seismic_severity", "unknown"),
    }
