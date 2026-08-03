"""Query API over a frozen market-discovery artifact.

No clustering runs at request time. Membership and PCA coordinates are read from the
versioned artifact built by ``scripts/build_market_discovery_artifact.py``.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from market_discovery.artifact import (
    DEFAULT_ARTIFACT_DIR,
    LoadedArtifact,
    artifact_meta_view,
    load_artifact,
)
from market_discovery.features import FEATURE_BY_ID
from market_discovery.geography_bridge import (
    GeographyLevelMismatch,
    atlas_slugs_for_geoid,
    county_geoid_for_atlas_slug,
)
from market_discovery.models import MarketArchetypeResult, PeerMarket
from models.provenance import DataClass, data_class_view


class UnknownMarketError(KeyError):
    pass


class MarketDiscoveryService:
    def __init__(self, artifact: LoadedArtifact) -> None:
        self.artifact = artifact

    def meta(self) -> dict:
        return artifact_meta_view(self.artifact)

    def clusters(self) -> list[dict]:
        return [
            {
                **summary.model_dump(mode="json"),
                "data_class": data_class_view(DataClass.PUBLIC_MARKET_DATA),
            }
            for summary in self.artifact.summaries
        ]

    def markets(self) -> list[dict]:
        return [
            {
                **row.model_dump(mode="json"),
                "data_class": data_class_view(DataClass.PUBLIC_MARKET_DATA),
                "atlas_slugs": atlas_slugs_for_geoid(row.geoid),
            }
            for row in sorted(self.artifact.assignments, key=lambda item: item.geoid)
        ]

    def pca_points(self) -> list[dict]:
        return [
            {
                "geoid": row.geoid,
                "name": row.name,
                "cluster_id": row.cluster_id,
                "label": row.label,
                "pca_x": row.pca_x,
                "pca_y": row.pca_y,
                "population": row.population,
                "in_clustering_universe": row.in_clustering_universe,
                "data_class": data_class_view(DataClass.PUBLIC_MARKET_DATA),
            }
            for row in sorted(self.artifact.assignments, key=lambda item: item.geoid)
        ]

    def resolve_geoid(self, market_id: str) -> str:
        """Accept a county GEOID or an Atlas demo slug."""
        if market_id.isdigit() and len(market_id) == 5:
            return market_id
        try:
            return county_geoid_for_atlas_slug(market_id)
        except GeographyLevelMismatch:
            raise
        # Fall through only if somehow not raised; keep mypy happy.
        raise UnknownMarketError(market_id)

    def market_profile(self, market_id: str, *, peer_count: int = 5) -> MarketArchetypeResult:
        try:
            geoid = self.resolve_geoid(market_id)
        except GeographyLevelMismatch:
            raise
        county = self.artifact.county(geoid)
        assignment = self.artifact.assignment(geoid)
        if county is None or assignment is None:
            raise UnknownMarketError(market_id)

        summary = self.artifact.summary(assignment.cluster_id)
        assert summary is not None

        peers = self._nearest_peers(geoid, assignment.cluster_id, peer_count=peer_count)
        caveats = [
            "Archetypes describe public county market structure, not store performance.",
            "Membership is deterministic for a given artifact version and seed.",
        ]
        if not assignment.in_clustering_universe:
            caveats.append(
                "This county is below the clustering population floor and was assigned "
                "to the nearest archetype centroid after the fit."
            )
        if market_id != geoid:
            caveats.append(
                f"Atlas geography {market_id!r} inherits the archetype of county GEOID {geoid}."
            )
        for feature_id, value in county.features.items():
            if value is None:
                caveats.append(
                    f"{FEATURE_BY_ID[feature_id].display_name} was missing and imputed "
                    f"under policy {FEATURE_BY_ID[feature_id].missing_policy}."
                )

        atlas_slug = market_id if market_id != geoid else None
        return MarketArchetypeResult(
            market_id=market_id,
            geoid=geoid,
            name=county.name,
            cluster_id=assignment.cluster_id,
            label=assignment.label,
            profile=dict(county.features),
            centroid_profile=dict(summary.centroid_features),
            nearest_markets=peers,
            distance_to_centroid=assignment.distance_to_centroid,
            pca_x=assignment.pca_x,
            pca_y=assignment.pca_y,
            quality=self.artifact.meta.quality,
            caveats=caveats,
            data_class=DataClass.PUBLIC_MARKET_DATA,
            assignment_method=assignment.assignment_method,
            atlas_slug=atlas_slug,
        )

    def market_profile_view(self, market_id: str, *, peer_count: int = 5) -> dict:
        result = self.market_profile(market_id, peer_count=peer_count)
        payload = result.model_dump(mode="json")
        payload["data_class"] = data_class_view(result.data_class)
        return payload

    def _nearest_peers(
        self,
        geoid: str,
        cluster_id: str,
        *,
        peer_count: int,
    ) -> list[PeerMarket]:
        target = self.artifact.assignment(geoid)
        assert target is not None
        target_xy = np.array([target.pca_x, target.pca_y], dtype=float)
        ranked: list[tuple[int, float, PeerMarket]] = []
        for row in self.artifact.assignments:
            if row.geoid == geoid:
                continue
            # Prefer same cluster; fall back to global nearest if the cluster is tiny.
            same = row.cluster_id == cluster_id
            dist = float(
                np.linalg.norm(np.array([row.pca_x, row.pca_y]) - target_xy)
            )
            ranked.append(
                (
                    0 if same else 1,
                    dist,
                    PeerMarket(
                        geoid=row.geoid,
                        name=row.name,
                        cluster_id=row.cluster_id,
                        label=row.label,
                        distance=dist,
                        population=row.population,
                    ),
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1], item[2].geoid))
        return [item[2] for item in ranked[:peer_count]]


@lru_cache(maxsize=1)
def get_market_discovery_service(directory: str | None = None) -> MarketDiscoveryService:
    path = str(directory) if directory else str(DEFAULT_ARTIFACT_DIR)
    return MarketDiscoveryService(load_artifact(path))


def clear_service_cache() -> None:
    get_market_discovery_service.cache_clear()
