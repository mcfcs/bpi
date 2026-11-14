"""Location vocabulary used to compare study populations and describe them.

Locations are expanded to Philippine administrative regions so that "Nationwide", "NCR", "Cebu"
and "Visayas" can be compared. Whether S&I will supply a fixed list of regions (and age bands) is
still open; until then this map is the one place to extend.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

REGION_ISLAND_GROUP: dict[str, str] = {
    "NCR": "Luzon",
    "CAR": "Luzon",
    "Ilocos": "Luzon",
    "Cagayan Valley": "Luzon",
    "Central Luzon": "Luzon",
    "Calabarzon": "Luzon",
    "Mimaropa": "Luzon",
    "Bicol": "Luzon",
    "Western Visayas": "Visayas",
    "Central Visayas": "Visayas",
    "Eastern Visayas": "Visayas",
    "Zamboanga Peninsula": "Mindanao",
    "Northern Mindanao": "Mindanao",
    "Davao": "Mindanao",
    "Soccsksargen": "Mindanao",
    "Caraga": "Mindanao",
    "BARMM": "Mindanao",
}

ISLAND_GROUPS = ("Luzon", "Visayas", "Mindanao")


def _regions_in(group: str) -> list[str]:
    return [region for region, g in REGION_ISLAND_GROUP.items() if g == group]


# Cities, provinces and group names mapped to administrative regions.
ALIASES: dict[str, list[str]] = {
    **{region.lower(): [region] for region in REGION_ISLAND_GROUP},
    "metro manila": ["NCR"],
    "manila": ["NCR"],
    "quezon city": ["NCR"],
    "makati": ["NCR"],
    "pasig": ["NCR"],
    "baguio": ["CAR"],
    "pampanga": ["Central Luzon"],
    "bulacan": ["Central Luzon"],
    "cavite": ["Calabarzon"],
    "laguna": ["Calabarzon"],
    "batangas": ["Calabarzon"],
    "rizal": ["Calabarzon"],
    "cebu": ["Central Visayas"],
    "cebu city": ["Central Visayas"],
    "bohol": ["Central Visayas"],
    "iloilo": ["Western Visayas"],
    "iloilo city": ["Western Visayas"],
    "bacolod": ["Western Visayas"],
    "negros occidental": ["Western Visayas"],
    "tacloban": ["Eastern Visayas"],
    "leyte": ["Eastern Visayas"],
    "davao city": ["Davao"],
    "cagayan de oro": ["Northern Mindanao"],
    "zamboanga": ["Zamboanga Peninsula"],
    "general santos": ["Soccsksargen"],
    "luzon": _regions_in("Luzon"),
    "visayas": _regions_in("Visayas"),
    "mindanao": _regions_in("Mindanao"),
    "nationwide": list(REGION_ISLAND_GROUP),
    "philippines": list(REGION_ISLAND_GROUP),
    "national": list(REGION_ISLAND_GROUP),
    # Areas defined by what they exclude or by settlement type, as reports often split results.
    "luzon outside ncr": [r for r in _regions_in("Luzon") if r != "NCR"],
    "provincial luzon": [r for r in _regions_in("Luzon") if r != "NCR"],
    "balance luzon": [r for r in _regions_in("Luzon") if r != "NCR"],
    "outside metro manila": [r for r in REGION_ISLAND_GROUP if r != "NCR"],
    "outside ncr": [r for r in REGION_ISLAND_GROUP if r != "NCR"],
    "rural luzon": [r for r in _regions_in("Luzon") if r != "NCR"],
    "rural visayas": _regions_in("Visayas"),
    "rural mindanao": _regions_in("Mindanao"),
}

# Highly urbanised cities outside Metro Manila. A study run only in these is "provincial cities";
# one that names provinces or island groups is "provincial"; one that says "rural" is "rural".
PROVINCIAL_CITIES = frozenset({
    "baguio", "cebu city", "iloilo city", "bacolod", "tacloban", "davao city", "cagayan de oro",
    "zamboanga", "general santos",
})
METRO_MANILA_NAMES = frozenset({"ncr", "metro manila", "manila", "quezon city", "makati", "pasig"})

AREA_LABELS: dict[str, str] = {
    "metro_manila": "Metro Manila (urban)",
    "provincial_city": "provincial cities",
    "provincial": "provincial areas outside Metro Manila",
    "rural": "rural areas",
    "mixed": "Metro Manila and provincial areas",
    "nationwide": "nationwide",
}

NATIONWIDE = frozenset({"nationwide", "philippines", "national"})


def expand(locations: Iterable[str] | None) -> set[str]:
    """Administrative regions covered by a list of locations. Unknown names are kept as-is so two
    studies that use the same unknown name still compare as the same place."""
    regions: set[str] = set()
    for location in locations or ():
        key = location.strip().lower()
        if key:
            regions.update(ALIASES.get(key, [location.strip()]))
    return regions


def island_groups(locations: Iterable[str] | None) -> list[str]:
    groups = {REGION_ISLAND_GROUP[r] for r in expand(locations) if r in REGION_ISLAND_GROUP}
    return [g for g in ISLAND_GROUPS if g in groups]


def is_nationwide(locations: Iterable[str] | None) -> bool:
    return any(loc.strip().lower() in NATIONWIDE for loc in locations or ())


def describe(locations: Iterable[str] | None) -> str:
    """Human label such as "Cebu and Iloilo (Visayas)", "NCR" or "Nationwide"."""
    locations = [loc for loc in locations or () if loc.strip()]
    if not locations:
        return "Location not stated"
    if is_nationwide(locations):
        return "Nationwide"
    names = locations[0] if len(locations) == 1 else ", ".join(locations[:-1]) + " and " + locations[-1]
    groups = island_groups(locations)
    # Don't repeat an island group the names already mention ("Rural Mindanao (Mindanao)").
    named_groups = {g for g in ISLAND_GROUPS if g.lower() in names.lower()}
    if len(groups) == 1 and not named_groups and names != "NCR":
        return f"{names} ({groups[0]})"
    return names


def area_type(locations: Iterable[str] | None) -> str | None:
    """Urban / provincial / rural reading of a list of locations, where the names allow one:
    metro_manila, provincial_city, provincial, rural, mixed or nationwide. None when no location
    is stated or none is recognised."""
    names = [loc.strip().lower() for loc in locations or () if loc.strip()]
    if not names:
        return None
    if is_nationwide(names):
        return "nationwide"
    regions = expand(names)
    if not regions & set(REGION_ISLAND_GROUP):
        return None
    if regions == {"NCR"}:
        return "metro_manila"
    if "NCR" in regions:
        return "mixed"
    if all(n.startswith("rural") for n in names):
        return "rural"
    if all(n in PROVINCIAL_CITIES for n in names):
        return "provincial_city"
    return "provincial"


def area_label(locations: Iterable[str] | None) -> str | None:
    kind = area_type(locations)
    return AREA_LABELS.get(kind) if kind else None


def where_phrase(locations: Iterable[str] | None) -> str:
    """"in Metro Manila", "in Cebu and Iloilo", "in rural Mindanao", "nationwide": the place as a
    phrase for running text, without parentheses (study details follow in parentheses)."""
    locations = [loc.strip() for loc in locations or () if loc.strip()]
    if not locations:
        return ""
    kind = area_type(locations)
    if kind == "nationwide":
        return "nationwide"
    if kind == "metro_manila":
        return "in Metro Manila"
    names = locations[0] if len(locations) == 1 else ", ".join(locations[:-1]) + " and " + locations[-1]
    if kind == "rural":
        return "in " + names[:1].lower() + names[1:]
    return f"in {names}"


# Places a question can ask about. Checked in this order: "rural areas outside Metro Manila" is rural.
_Q_RURAL = re.compile(r"\b(?:rural|countryside|probinsya)\b", re.IGNORECASE)
_Q_OUTSIDE = re.compile(r"\b(?:outside (?:of )?(?:metro manila|ncr|manila)|the provinces?|provincial|provinces)\b",
                        re.IGNORECASE)
_Q_ISLAND = re.compile(r"\b(luzon|visayas|mindanao)\b", re.IGNORECASE)
_Q_METRO = re.compile(r"\b(?:metro manila|ncr|manila)\b", re.IGNORECASE)
QUESTION_AREA_PHRASES = {"rural": "rural areas", "provincial": "areas outside Metro Manila",
                         "metro_manila": "Metro Manila"}


def question_area(question: str | None) -> str | None:
    """The place a question asks about: "rural", "provincial" (outside Metro Manila), "metro_manila"
    or an island group ("Visayas"); None when it names none. Used so a headline answers for that place
    rather than leading with another place's figure."""
    q = question or ""
    if _Q_RURAL.search(q):
        return "rural"
    if _Q_OUTSIDE.search(q):
        return "provincial"
    island = _Q_ISLAND.search(q)
    if island:
        return island.group(1).capitalize()
    if _Q_METRO.search(q):
        return "metro_manila"
    return None


def in_area(area: str, locations: Iterable[str] | None, segment: str | None = None) -> bool:
    """Whether a finding's population (its regions, and a segment such as "Customers in rural
    barangays") lies in the area a question asks about."""
    kind = area_type(locations)
    rural_segment = "rural" in (segment or "").lower()
    if area == "rural":
        return kind == "rural" or rural_segment
    if area == "provincial":
        return kind in ("provincial", "provincial_city", "rural") or rural_segment
    if area == "metro_manila":
        return kind == "metro_manila"
    if area in ISLAND_GROUPS:
        return kind not in (None, "nationwide", "mixed") and island_groups(locations) == [area]
    return False


def contrast_note(a: Iterable[str] | None, b: Iterable[str] | None) -> str | None:
    """A short urban/provincial reading of two places, when they fall on different sides:
    "Metro Manila compared with provincial areas"."""
    ka, kb = area_type(a), area_type(b)
    if not ka or not kb or ka == kb:
        return None
    if "metro_manila" in (ka, kb):
        other = kb if ka == "metro_manila" else ka
        if other in ("provincial", "provincial_city", "rural"):
            return f"Metro Manila compared with {AREA_LABELS[other].replace(' outside Metro Manila', '')}"
        if other == "nationwide":
            return "Metro Manila compared with the whole country"
    if {"rural"} & {ka, kb} and {"provincial_city", "metro_manila"} & {ka, kb}:
        return "urban compared with rural areas"
    return None
