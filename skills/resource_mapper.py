"""
Resource Mapper
================

Maps a triaged incident (severity tier + detected hazard keywords) to a
concrete, dispatchable list of response units.

The base mapping is tier-driven (a "High" incident always gets at least a
fire brigade + ambulance + police unit, regardless of what kind of hazard it
is), but real dispatch decisions also depend on *what* is happening --
an explosion needs a bomb disposal/HazMat unit even at "Medium" severity,
a flood needs water rescue and not a fire brigade, etc. `map_resources`
layers hazard-specific units on top of the tier baseline so the
recommendation reads as something an actual dispatcher would send.
"""

from __future__ import annotations

# ---------------------------------------------------------------------
# Tier baseline: the minimum response for any incident at this severity,
# independent of hazard type.
# ---------------------------------------------------------------------
TIER_BASE_RESOURCES = {
    "Low": ["Local notification"],
    "Medium": ["Police unit", "Traffic control"],
    "High": ["Fire brigade", "Ambulance", "Police unit"],
    "Critical": [
        "Multi-unit fire response",
        "Advanced life support ambulance",
        "Police command",
        "Disaster management cell",
    ],
}

DEFAULT_TIER = "Low"

# ---------------------------------------------------------------------
# Hazard-specific additions. These are layered on top of the tier
# baseline -- e.g. a "Medium" explosion gets "Police unit, Traffic
# control" PLUS "Bomb disposal squad" and "HazMat unit".
#
# Kept deliberately conservative: hazard additions only kick in once an
# incident has cleared "Low" severity, so a single ambiguous keyword hit
# on an otherwise low-confidence report doesn't trigger a heavy unit
# dispatch on its own (severity scoring already gates that upstream).
# ---------------------------------------------------------------------
HAZARD_RESOURCE_ADDITIONS = {
    "fire": ["Fire brigade"],
    "smoke": ["Fire brigade"],
    "explosion": ["Bomb disposal squad", "HazMat unit"],
    "flood": ["Water rescue team", "Boat unit"],
    "collapse": ["Urban search and rescue (USAR)", "Structural engineer"],
    "injured": ["Ambulance", "Paramedic team"],
    "trapped": ["Urban search and rescue (USAR)"],
    "earthquake": ["Urban search and rescue (USAR)", "Structural engineer"],
    "tsunami": ["Coastal evacuation team", "Water rescue team"],
    "landslide": ["Urban search and rescue (USAR)", "Heavy equipment team"],
    "accident": ["Ambulance", "Traffic control"],
    "chemical": ["HazMat unit", "Decontamination team"],
    "medical": ["Advanced life support ambulance", "Paramedic team"],
}

# Hazards severe enough to warrant pulling in resources even on a
# moderate-severity incident (used by `is_priority_hazard`).
HIGH_PRIORITY_HAZARDS = {"explosion", "collapse", "earthquake", "tsunami", "landslide"}


def map_resources(severity_tier: str, hazards: "list[str] | None" = None) -> "list[str]":
    """
    Return the recommended response units for an incident.

    Parameters
    ----------
    severity_tier:
        One of "Low", "Medium", "High", "Critical" (as produced by
        `skills.severity_score.severity_tier`). Unknown/missing tiers
        fall back to the "Low" baseline so this never raises on bad
        input -- a malformed tier should not block dispatch of *some*
        response.
    hazards:
        Optional list of hazard keys (as produced by
        `skills.severity_score.score_from_text`'s `hits`, e.g.
        ["fire", "smoke"]). When provided, hazard-specific units are
        layered on top of the tier baseline. Omit this to get the
        tier-only baseline (e.g. for quick lookups or tests).

    Returns
    -------
    A de-duplicated, order-preserving list of unit names: tier baseline
    first, then any additional hazard-specific units not already
    covered by the baseline.
    """
    base = list(TIER_BASE_RESOURCES.get(severity_tier, TIER_BASE_RESOURCES[DEFAULT_TIER]))

    if not hazards or severity_tier == "Low":
        return base

    resources = list(base)
    for hazard in hazards:
        for unit in HAZARD_RESOURCE_ADDITIONS.get(hazard, []):
            if unit not in resources:
                resources.append(unit)

    return resources


def is_priority_hazard(hazards: "list[str] | None") -> bool:
    """True if any detected hazard warrants escalated handling regardless
    of the numeric severity score (e.g. an explosion mention should never
    be quietly triaged as routine)."""
    if not hazards:
        return False
    return any(hazard in HIGH_PRIORITY_HAZARDS for hazard in hazards)


def describe_resources(resources: "list[str]") -> str:
    """Human-readable, comma-separated summary for dispatch messages."""
    if not resources:
        return "No units recommended"
    return ", ".join(resources)