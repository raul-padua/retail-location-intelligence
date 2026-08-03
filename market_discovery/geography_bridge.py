"""Map Atlas demo geography slugs onto county GEOIDs for archetype lookup.

Cities inherit their parent county archetype. CBSA / congressional districts are not
county-level and therefore refuse archetype membership rather than inventing one.
"""

from __future__ import annotations

# GEOID = state FIPS (2) + county FIPS (3), matching Census / ACS.
CHITTENDEN = "50007"
FRANKLIN = "50011"
GRAND_ISLE = "50013"

_ATLAS_SLUG_TO_COUNTY: dict[str, str] = {
    "county:chittenden-county-vt": CHITTENDEN,
    "county:franklin-county-vt": FRANKLIN,
    "county:grand-isle-county-vt": GRAND_ISLE,
    "city:burlington-vt": CHITTENDEN,
    "city:colchester-vt": CHITTENDEN,
    "city:essex-junction-vt": CHITTENDEN,
    "city:essex-vt": CHITTENDEN,
    "city:jericho-vt": CHITTENDEN,
    "city:milton-vt": CHITTENDEN,
    "city:shelburne-vt": CHITTENDEN,
    "city:south-burlington-vt": CHITTENDEN,
    "city:williston-vt": CHITTENDEN,
    "city:winooski-vt": CHITTENDEN,
    "city:st-albans-city-vt": FRANKLIN,
    "city:st-albans-town-vt": FRANKLIN,
    "city:swanton-vt": FRANKLIN,
}


class GeographyLevelMismatch(ValueError):
    """Raised when an Atlas geography cannot map to a county archetype."""


def county_geoid_for_atlas_slug(slug: str) -> str:
    geoid = _ATLAS_SLUG_TO_COUNTY.get(slug)
    if geoid is None:
        raise GeographyLevelMismatch(
            f"{slug!r} is not a county-mappable Atlas demo geography. "
            "Archetypes are defined on U.S. counties; CBSA and congressional districts "
            "must be compared via their constituent counties."
        )
    return geoid


def atlas_slugs_for_geoid(geoid: str) -> list[str]:
    return sorted(slug for slug, mapped in _ATLAS_SLUG_TO_COUNTY.items() if mapped == geoid)
