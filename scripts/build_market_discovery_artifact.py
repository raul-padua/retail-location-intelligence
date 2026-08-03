"""Build the versioned market-discovery clustering artifact.

Default path (offline / CI):

    uv run python scripts/build_market_discovery_artifact.py

Optional live ACS pull (network; marks provenance accordingly):

    uv run python scripts/build_market_discovery_artifact.py --source acs

The committed ``data/market_discovery/v1/`` artifact is the demo path. Live refresh is
for regenerating that cache, not for request-time clustering.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_discovery.artifact import (  # noqa: E402
    ARTIFACT_VERSION,
    DEFAULT_ARTIFACT_DIR,
    write_artifact,
)
from market_discovery.cluster import (  # noqa: E402
    _canonical_cluster_id,
    _default_label,
    fit_clusters,
    nearest_centroid_label,
    project_pca,
)
from market_discovery.features import FEATURE_SET_VERSION  # noqa: E402
from market_discovery.fixture_counties import (  # noqa: E402
    assert_finite_features,
    build_fixture_counties,
)
from market_discovery.models import (  # noqa: E402
    ClusterArtifactMeta,
    MarketAssignment,
)
from market_discovery.pipeline import (  # noqa: E402
    DEFAULT_K_RANGE,
    DEFAULT_MIN_POPULATION,
    DEFAULT_SEED,
    MODEL_VERSION,
    prepare_matrix,
    scale_rows,
)
from models.provenance import DataClass  # noqa: E402


def _prepare_row_raw(county, feature_ids: tuple[str, ...]) -> np.ndarray:
    from market_discovery.pipeline import _apply_transform, _impute_column
    from market_discovery.features import FEATURE_BY_ID

    values = []
    for feature_id in feature_ids:
        raw = county.features.get(feature_id)
        arr = np.array(
            [float("nan") if raw is None else float(raw)],
            dtype=float,
        )
        imputed = _impute_column(arr, FEATURE_BY_ID[feature_id].missing_policy)
        values.append(float(_apply_transform(feature_id, imputed)[0]))
    return np.asarray(values, dtype=float)


def build(
    *,
    output: Path,
    source: str,
    seed: int,
    min_population: int,
    k_range: tuple[int, int],
) -> Path:
    if source == "acs":
        raise SystemExit(
            "Live ACS acquisition is not wired in this build yet. "
            "Use --source fixture (default) and refresh from Census offline when ready."
        )

    counties = build_fixture_counties(min_population=min_population)
    assert_finite_features(counties)
    prepared = prepare_matrix(
        counties,
        seed=seed,
        min_population=min_population,
        k_range=k_range,
        universe_only=True,
    )
    fit = fit_clusters(prepared, seed=seed, k_range=k_range)

    geoid_to_county = {county.geoid: county for county in counties}
    assignments: list[MarketAssignment] = []
    fit_index = {geoid: i for i, geoid in enumerate(prepared.geoids)}

    for geoid in prepared.geoids:
        county = geoid_to_county[geoid]
        i = fit_index[geoid]
        cluster_id = fit.cluster_ids[i]
        dist = float(
            np.linalg.norm(prepared.scaled[i] - fit.centroids_scaled[fit.labels[i]])
        )
        assignments.append(
            MarketAssignment(
                geoid=geoid,
                name=county.name,
                cluster_id=cluster_id,
                label=_default_label(cluster_id),
                distance_to_centroid=dist,
                pca_x=float(fit.pca_coords[i, 0]),
                pca_y=float(fit.pca_coords[i, 1]),
                lat=county.lat,
                lon=county.lon,
                population=county.population,
                in_clustering_universe=True,
                assignment_method="kmeans",
            )
        )

    # Post-hoc nearest-centroid for counties below the population floor.
    for county in sorted(counties, key=lambda item: item.geoid):
        if county.geoid in fit_index:
            continue
        raw = _prepare_row_raw(county, prepared.feature_ids)
        scaled = scale_rows(prepared, raw.reshape(1, -1))[0]
        label_idx, dist = nearest_centroid_label(scaled, fit.centroids_scaled)
        cluster_id = _canonical_cluster_id(label_idx)
        pca_xy = project_pca(
            scaled.reshape(1, -1),
            fit.pca_components,
            fit.pca_mean,
        )[0]
        assignments.append(
            MarketAssignment(
                geoid=county.geoid,
                name=county.name,
                cluster_id=cluster_id,
                label=_default_label(cluster_id),
                distance_to_centroid=dist,
                pca_x=float(pca_xy[0]),
                pca_y=float(pca_xy[1]),
                lat=county.lat,
                lon=county.lon,
                population=county.population,
                in_clustering_universe=False,
                assignment_method="nearest_centroid",
            )
        )

    assignments.sort(key=lambda row: row.geoid)
    meta = ClusterArtifactMeta(
        artifact_version=ARTIFACT_VERSION,
        feature_set_version=FEATURE_SET_VERSION,
        model_version=MODEL_VERSION,
        seed=seed,
        config_hash=prepared.config_hash,
        k=fit.quality.k,
        min_population=min_population,
        n_counties_fit=len(prepared.geoids),
        n_counties_total=len(counties),
        data_class=DataClass.PUBLIC_MARKET_DATA,
        quality=fit.quality,
        provenance_notes=[
            "Fixture counties are ACS-shaped public-market features for offline demos.",
            "Feature ids and ACS variable references are in the feature registry.",
            "K-means membership is deterministic for this seed and config hash.",
            "Counties below min_population are assigned by nearest centroid after fit.",
        ],
    )

    write_artifact(
        output,
        counties=sorted(counties, key=lambda c: c.geoid),
        assignments=assignments,
        summaries=list(fit.summaries),
        meta=meta,
        feature_ids=list(prepared.feature_ids),
        scaler_mean=list(prepared.scaler_mean),
        scaler_scale=list(prepared.scaler_scale),
        centroids_scaled=fit.centroids_scaled.tolist(),
        pca_components=fit.pca_components.tolist(),
        pca_mean=fit.pca_mean.tolist(),
        dropped_correlated=list(prepared.dropped_correlated),
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help="Directory for manifest/counties/assignments/clusters JSON",
    )
    parser.add_argument(
        "--source",
        choices=("fixture", "acs"),
        default="fixture",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--min-population", type=int, default=DEFAULT_MIN_POPULATION)
    parser.add_argument("--k-min", type=int, default=DEFAULT_K_RANGE[0])
    parser.add_argument("--k-max", type=int, default=DEFAULT_K_RANGE[1])
    args = parser.parse_args()
    path = build(
        output=args.output,
        source=args.source,
        seed=args.seed,
        min_population=args.min_population,
        k_range=(args.k_min, args.k_max),
    )
    print(f"Wrote market discovery artifact to {path}")


if __name__ == "__main__":
    main()
