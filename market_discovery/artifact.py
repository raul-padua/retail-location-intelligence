"""Load and persist versioned market-discovery artifacts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from market_discovery.features import FEATURE_SET_VERSION, feature_registry_view
from market_discovery.models import (
    ClusterArtifactMeta,
    ClusterSummary,
    CountyRecord,
    MarketAssignment,
    QualityReport,
)
from models.provenance import DataClass, data_class_view

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "market_discovery" / "v1"
ARTIFACT_VERSION = "v1"


class ArtifactError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise ArtifactError(f"Missing artifact file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_artifact(
    directory: Path,
    *,
    counties: list[CountyRecord],
    assignments: list[MarketAssignment],
    summaries: list[ClusterSummary],
    meta: ClusterArtifactMeta,
    feature_ids: list[str],
    scaler_mean: list[float],
    scaler_scale: list[float],
    centroids_scaled: list[list[float]],
    pca_components: list[list[float]],
    pca_mean: list[float],
    dropped_correlated: list[str],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "artifact_version": meta.artifact_version,
        "feature_set_version": meta.feature_set_version,
        "model_version": meta.model_version,
        "seed": meta.seed,
        "config_hash": meta.config_hash,
        "k": meta.k,
        "min_population": meta.min_population,
        "n_counties_fit": meta.n_counties_fit,
        "n_counties_total": meta.n_counties_total,
        "data_class": str(meta.data_class),
        "quality": meta.quality.model_dump(mode="json"),
        "provenance_notes": meta.provenance_notes,
        "feature_ids": feature_ids,
        "dropped_correlated": dropped_correlated,
        "scaler_mean": scaler_mean,
        "scaler_scale": scaler_scale,
        "centroids_scaled": centroids_scaled,
        "pca_components": pca_components,
        "pca_mean": pca_mean,
        "features": feature_registry_view(),
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (directory / "counties.json").write_text(
        json.dumps(
            [county.model_dump(mode="json") for county in counties],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (directory / "assignments.json").write_text(
        json.dumps(
            [row.model_dump(mode="json") for row in assignments],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (directory / "clusters.json").write_text(
        json.dumps(
            [row.model_dump(mode="json") for row in summaries],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


class LoadedArtifact:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        manifest = _read_json(directory / "manifest.json")
        self.manifest = manifest
        self.counties = [
            CountyRecord.model_validate(row)
            for row in _read_json(directory / "counties.json")
        ]
        self.assignments = [
            MarketAssignment.model_validate(row)
            for row in _read_json(directory / "assignments.json")
        ]
        self.summaries = [
            ClusterSummary.model_validate(row)
            for row in _read_json(directory / "clusters.json")
        ]
        self._by_geoid = {county.geoid: county for county in self.counties}
        self._assignment_by_geoid = {
            row.geoid: row for row in self.assignments
        }
        self._summary_by_id = {row.cluster_id: row for row in self.summaries}
        if manifest.get("feature_set_version") != FEATURE_SET_VERSION:
            raise ArtifactError(
                f"Artifact feature set {manifest.get('feature_set_version')!r} does not "
                f"match code registry {FEATURE_SET_VERSION!r}"
            )

    @property
    def meta(self) -> ClusterArtifactMeta:
        quality = QualityReport.model_validate(self.manifest["quality"])
        return ClusterArtifactMeta(
            artifact_version=self.manifest["artifact_version"],
            feature_set_version=self.manifest["feature_set_version"],
            model_version=self.manifest["model_version"],
            seed=int(self.manifest["seed"]),
            config_hash=self.manifest["config_hash"],
            k=int(self.manifest["k"]),
            min_population=int(self.manifest["min_population"]),
            n_counties_fit=int(self.manifest["n_counties_fit"]),
            n_counties_total=int(self.manifest["n_counties_total"]),
            data_class=DataClass(self.manifest.get("data_class", DataClass.PUBLIC_MARKET_DATA)),
            quality=quality,
            provenance_notes=list(self.manifest.get("provenance_notes", [])),
        )

    def county(self, geoid: str) -> CountyRecord | None:
        return self._by_geoid.get(geoid)

    def assignment(self, geoid: str) -> MarketAssignment | None:
        return self._assignment_by_geoid.get(geoid)

    def summary(self, cluster_id: str) -> ClusterSummary | None:
        return self._summary_by_id.get(cluster_id)


@lru_cache(maxsize=4)
def load_artifact(directory: str | None = None) -> LoadedArtifact:
    path = Path(directory) if directory else DEFAULT_ARTIFACT_DIR
    return LoadedArtifact(path.resolve())


def clear_artifact_cache() -> None:
    load_artifact.cache_clear()


def artifact_meta_view(artifact: LoadedArtifact) -> dict[str, Any]:
    meta = artifact.meta
    return {
        **meta.model_dump(mode="json"),
        "data_class": data_class_view(meta.data_class),
        "feature_ids": artifact.manifest["feature_ids"],
        "dropped_correlated": artifact.manifest.get("dropped_correlated", []),
        "features": artifact.manifest.get("features", feature_registry_view()),
    }
