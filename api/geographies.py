"""Geographies reachable with the public demo token.

Transcribed from StateBook's Authentication and Licensing article. The demo token is
limited to the Burlington-South Burlington, VT metro area, so this list doubles as the
allowlist that keeps untrusted user input from reaching the API as an arbitrary slug.
"""

from __future__ import annotations

import re

from models.geography import Geography, GeographyType

DEMO_TOKEN_SCOPE_NOTE = (
    "The public demo token only licenses the Burlington-South Burlington, VT metro area "
    "(Chittenden, Franklin, and Grand Isle counties and the cities within them). Regions "
    "outside that footprint require a commercial StateBook license."
)

_DEMO_SPECS: list[tuple[str, str]] = [
    ("county:chittenden-county-vt", "Chittenden County, VT"),
    ("county:franklin-county-vt", "Franklin County, VT"),
    ("county:grand-isle-county-vt", "Grand Isle County, VT"),
    ("cbsa:burlington-south-burlington-vt-metro-area", "Burlington-South Burlington, VT Metro Area"),
    ("city:burlington-vt", "Burlington, VT"),
    ("city:colchester-vt", "Colchester, VT"),
    ("city:essex-junction-vt", "Essex Junction, VT"),
    ("city:essex-vt", "Essex, VT"),
    ("city:jericho-vt", "Jericho, VT"),
    ("city:milton-vt", "Milton, VT"),
    ("city:shelburne-vt", "Shelburne, VT"),
    ("city:south-burlington-vt", "South Burlington, VT"),
    ("city:st-albans-city-vt", "St. Albans city, VT"),
    ("city:st-albans-town-vt", "St. Albans town, VT"),
    ("city:swanton-vt", "Swanton, VT"),
    ("city:williston-vt", "Williston, VT"),
    ("city:winooski-vt", "Winooski, VT"),
    ("congressionaldistrict:cd5000", "Vermont Congressional District (At Large)"),
]

DEMO_GEOGRAPHIES: dict[str, Geography] = {
    slug: Geography.parse(slug, display_name) for slug, display_name in _DEMO_SPECS
}

_SLUG_RE = re.compile(r"^[a-z]+:[a-z0-9-]+$")

# Free-text aliases so a user can type "Burlington" rather than a slug. Resolution is
# strictly lookup-based: an unmatched name is refused, never guessed into a slug.
_ALIASES: dict[str, str] = {}
for _slug, _name in _DEMO_SPECS:
    _ALIASES[_name.lower()] = _slug
    _ALIASES[_slug] = _slug
    _bare = _slug.split(":", 1)[1].replace("-", " ")
    _ALIASES[_bare] = _slug
    _ALIASES[_bare.removesuffix(" vt").strip()] = _slug
_ALIASES.update(
    {
        "burlington": "city:burlington-vt",
        "south burlington": "city:south-burlington-vt",
        "burlington metro": "cbsa:burlington-south-burlington-vt-metro-area",
        "burlington metro area": "cbsa:burlington-south-burlington-vt-metro-area",
        "chittenden": "county:chittenden-county-vt",
        "franklin": "county:franklin-county-vt",
        "grand isle": "county:grand-isle-county-vt",
    }
)


class UnsupportedGeographyError(ValueError):
    """Raised when a requested geography is not licensed by the active token."""

    def __init__(self, requested: str) -> None:
        self.requested = requested
        super().__init__(
            f"{requested!r} is not available with the current token. {DEMO_TOKEN_SCOPE_NOTE}"
        )


def is_demo_supported(slug: str) -> bool:
    return slug in DEMO_GEOGRAPHIES


def resolve_geography(user_input: str, *, restrict_to_demo: bool = True) -> Geography:
    """Resolve free text or a slug to an approved :class:`Geography`.

    ``restrict_to_demo`` exists so a licensed token can widen the allowlist later without
    changing call sites; it is left on for the prototype.
    """
    candidate = (user_input or "").strip().lower()
    if not candidate:
        raise UnsupportedGeographyError(user_input)

    slug = _ALIASES.get(candidate)
    if slug is None and _SLUG_RE.match(candidate):
        slug = candidate

    if slug is None:
        raise UnsupportedGeographyError(user_input)

    if restrict_to_demo:
        if slug not in DEMO_GEOGRAPHIES:
            raise UnsupportedGeographyError(user_input)
        return DEMO_GEOGRAPHIES[slug]

    return Geography.parse(slug)


def demo_geography_choices(
    types: tuple[GeographyType, ...] | None = None,
) -> list[Geography]:
    values = list(DEMO_GEOGRAPHIES.values())
    if types:
        values = [geography for geography in values if geography.geography_type in types]
    return sorted(values, key=lambda geography: (geography.resolution_rank, geography.display_name))
