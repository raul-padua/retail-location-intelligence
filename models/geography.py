"""Geography identifiers as understood by the Atlas API."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class GeographyType(StrEnum):
    COUNTRY = "country"
    STATE = "state"
    CBSA = "cbsa"
    COUNTY = "county"
    CITY = "city"
    CONGRESSIONAL_DISTRICT = "congressionaldistrict"
    SCHOOL_DISTRICT = "schooldistrict"
    CENSUS_TRACT = "censustract"
    BLOCK_GROUP = "blockgroup"


# Ordered coarse -> fine. Used to detect comparisons that mix resolutions.
RESOLUTION_ORDER: dict[GeographyType, int] = {
    GeographyType.COUNTRY: 0,
    GeographyType.STATE: 1,
    GeographyType.CBSA: 2,
    GeographyType.COUNTY: 3,
    GeographyType.CONGRESSIONAL_DISTRICT: 3,
    GeographyType.SCHOOL_DISTRICT: 4,
    GeographyType.CITY: 5,
    GeographyType.CENSUS_TRACT: 6,
    GeographyType.BLOCK_GROUP: 7,
}


class Geography(BaseModel):
    """An Atlas geography slug of the form ``type:name``."""

    model_config = {"frozen": True}

    slug: str = Field(description="Atlas geography identifier, e.g. 'city:burlington-vt'")
    display_name: str
    geography_type: GeographyType

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        if ":" not in value:
            raise ValueError(f"Geography slug must be 'type:name', got {value!r}")
        return value

    @property
    def resolution_rank(self) -> int:
        return RESOLUTION_ORDER[self.geography_type]

    @classmethod
    def parse(cls, slug: str, display_name: str | None = None) -> Geography:
        prefix, _, remainder = slug.partition(":")
        try:
            geography_type = GeographyType(prefix)
        except ValueError as exc:
            raise ValueError(f"Unsupported geography type {prefix!r} in {slug!r}") from exc
        return cls(
            slug=slug,
            display_name=display_name or remainder.replace("-", " ").title(),
            geography_type=geography_type,
        )
