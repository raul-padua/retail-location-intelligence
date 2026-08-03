"""Typed views for market-discovery artifacts and query results."""

from __future__ import annotations

from pydantic import BaseModel, Field

from models.provenance import DataClass


class CountyRecord(BaseModel):
    model_config = {"frozen": True}

    geoid: str
    name: str
    state_fips: str
    county_fips: str
    population: float
    land_area_sq_mi: float
    lat: float
    lon: float
    features: dict[str, float | None]
    in_clustering_universe: bool = True
    """False for counties kept for profile/lookup but excluded from K-means fit (e.g. <50k)."""


class ClusterSummary(BaseModel):
    model_config = {"frozen": True}

    cluster_id: str
    label: str
    member_count: int
    centroid_features: dict[str, float]
    distinctive_high: list[str] = Field(default_factory=list)
    distinctive_low: list[str] = Field(default_factory=list)


class MarketAssignment(BaseModel):
    model_config = {"frozen": True}

    geoid: str
    name: str
    cluster_id: str
    label: str
    distance_to_centroid: float
    pca_x: float
    pca_y: float
    lat: float
    lon: float
    population: float
    in_clustering_universe: bool
    assignment_method: str
    """``kmeans`` for fit members; ``nearest_centroid`` for post-hoc small counties."""


class QualityReport(BaseModel):
    model_config = {"frozen": True}

    k: int
    inertia: float
    silhouette: float
    selection_rule: str
    candidate_scores: dict[str, float] = Field(default_factory=dict)


class ClusterArtifactMeta(BaseModel):
    model_config = {"frozen": True}

    artifact_version: str
    feature_set_version: str
    model_version: str
    seed: int
    config_hash: str
    k: int
    min_population: int
    n_counties_fit: int
    n_counties_total: int
    data_class: DataClass = DataClass.PUBLIC_MARKET_DATA
    quality: QualityReport
    provenance_notes: list[str] = Field(default_factory=list)


class PeerMarket(BaseModel):
    model_config = {"frozen": True}

    geoid: str
    name: str
    cluster_id: str
    label: str
    distance: float
    population: float


class MarketArchetypeResult(BaseModel):
    model_config = {"frozen": True}

    market_id: str
    geoid: str
    name: str
    cluster_id: str
    label: str
    profile: dict[str, float | None]
    centroid_profile: dict[str, float]
    nearest_markets: list[PeerMarket]
    distance_to_centroid: float
    pca_x: float
    pca_y: float
    quality: QualityReport
    caveats: list[str]
    data_class: DataClass = DataClass.PUBLIC_MARKET_DATA
    assignment_method: str
    atlas_slug: str | None = None
