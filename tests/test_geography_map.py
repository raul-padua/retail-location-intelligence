"""Map presentation data for the licensed demo footprint.

Centroids are not analytical inputs. These tests pin that every allowlisted geography
projects a lat/lon for the workspace map, and that the projection carries an Atlas
data-class badge rather than inventing a different provenance.
"""

from __future__ import annotations

from api.geographies import DEMO_GEOGRAPHIES, centroid_for
from models.provenance import DataClass
from server.views import catalog_view, geography_view
from planning.capabilities import get_capability_registry
from metrics.registry import get_registry


def test_every_demo_geography_has_a_centroid():
    missing = [slug for slug in DEMO_GEOGRAPHIES if centroid_for(slug) is None]
    assert missing == []


def test_geography_view_carries_atlas_data_class_and_coordinates():
    geography = DEMO_GEOGRAPHIES["city:burlington-vt"]
    projected = geography_view(geography)

    assert projected["slug"] == "city:burlington-vt"
    assert projected["lat"] == 44.4759
    assert projected["lon"] == -73.2121
    assert projected["data_class"]["data_class"] == DataClass.ATLAS_EVIDENCE
    assert "Atlas" in projected["data_class"]["label"]


def test_catalog_exposes_data_classes_and_geo_centroids():
    catalog = catalog_view(get_registry(), get_capability_registry())

    assert {entry["data_class"] for entry in catalog["data_classes"]} == {
        str(entry) for entry in DataClass
    }
    burlington = next(
        geo for geo in catalog["geographies"] if geo["slug"] == "city:burlington-vt"
    )
    assert burlington["lat"] is not None
    assert burlington["lon"] is not None
