HAZARD_KEYWORDS = {
    "fire": {
        "weight": 35,
        "keywords": ["fire", "flames", "blaze", "burning", "forest fire", "wildfire"]
    },
    "explosion": {
        "weight": 45,
        "keywords": ["explosion", "blast", "detonation", "bomb"]
    },
    "smoke": {
        "weight": 20,
        "keywords": ["smoke", "smoke plume", "thick smoke"]
    },
    "flood": {
        "weight": 30,
        "keywords": ["flood", "flooding", "waterlogging", "overflow", "inundation"]
    },
    "collapse": {
        "weight": 50,
        "keywords": ["collapse", "collapsed", "building collapse"]
    },
    "injured": {
        "weight": 25,
        "keywords": ["injured", "injury", "wounded", "casualty"]
    },
    "trapped": {
        "weight": 30,
        "keywords": ["trapped", "stuck", "trapped inside"]
    },
    "earthquake": {
        "weight": 45,
        "keywords": ["earthquake", "quake", "tremor", "seismic"]
    },
    "tsunami": {
        "weight": 50,
        "keywords": ["tsunami", "tidal wave"]
    },
    "landslide": {
        "weight": 40,
        "keywords": ["landslide", "mudslide", "rockslide"]
    },
    "accident":{
        "weight": 20,
        "keywords": ["accident", "collision", "crash", "wreck", "breakdown"]     
    },
    "chemical": {
        "weight": 40,
        "keywords": ["chemical spill", "toxic", "hazardous material", "hazmat", "gas leak", "poisonous"]
    },
    "medical": {
        "weight": 35,
        "keywords": ["heart attack", "unconscious", "not breathing", "seizure", "bleeding profusely"]
    }
}


def score_from_text(text: str):
    text = text.lower()

    score = 0
    hits = []

    for hazard, info in HAZARD_KEYWORDS.items():
        for keyword in info["keywords"]:
            if keyword in text:
                score += info["weight"]

                if hazard not in hits:
                    hits.append(hazard)

                break

    return min(score, 100), hits


def combine_scores(
    rule_score: int,
    llm_score: int = 50,
    weather_boost: int = 0
):
    final_score = (
        0.5 * rule_score +
        0.3 * llm_score +
        0.2 * weather_boost
    )

    return min(round(final_score), 100)


def severity_tier(score: int):

    if score >= 80:
        return "Critical"

    elif score >= 60:
        return "High"

    elif score >= 30:
        return "Medium"

    return "Low"


def detect_primary_hazard(text: str):
    """
    Return the highest-priority hazard detected in the report.
    """

    _, hits = score_from_text(text)

    if not hits:
        return None

    highest = max(
        hits,
        key=lambda hazard: HAZARD_KEYWORDS[hazard]["weight"]
    )

    return highest