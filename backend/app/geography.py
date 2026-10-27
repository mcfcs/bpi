"""Location vocabulary used to compare study populations and describe them.

Locations are expanded to Philippine administrative regions so that "Nationwide", "NCR", "Cebu"
and "Visayas" can be compared. Whether S&I will supply a fixed list of regions (and age bands) is
still open; until then this map is the one place to extend.
"""

from __future__ import annotations

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
    named_groups = {loc.strip().lower() for loc in locations} & {g.lower() for g in ISLAND_GROUPS}
    if len(groups) == 1 and not named_groups and names != "NCR":
        return f"{names} ({groups[0]})"
    return names
