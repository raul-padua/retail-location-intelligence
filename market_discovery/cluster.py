"""Deterministic K-means archetypes with canonical cluster ids.

Canonicalization reorders labels by descending mean of the first retained feature among
members, then assigns ``A01``…``A0k``. That keeps ids stable when the input county list is
shuffled before preparation (preparation itself sorts by geoid).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

from market_discovery.models import ClusterSummary, QualityReport
from market_discovery.pipeline import (
    DEFAULT_K_RANGE,
    DEFAULT_SEED,
    PreparedMatrix,
)


@dataclass(frozen=True)
class ClusterFit:
    labels: np.ndarray  # canonical 0..k-1 aligned to prepared.geoids
    cluster_ids: tuple[str, ...]  # per row, e.g. A03
    summaries: tuple[ClusterSummary, ...]
    quality: QualityReport
    centroids_scaled: np.ndarray
    pca_coords: np.ndarray  # n x 2
    pca_components: np.ndarray
    pca_mean: np.ndarray


def _canonical_cluster_id(index: int) -> str:
    return f"A{index + 1:02d}"


def _default_label(cluster_id: str) -> str:
    return f"Archetype {cluster_id[1:]}"


def fit_clusters(
    prepared: PreparedMatrix,
    *,
    seed: int = DEFAULT_SEED,
    k_range: tuple[int, int] = DEFAULT_K_RANGE,
) -> ClusterFit:
    low, high = k_range
    candidate_scores: dict[str, float] = {}
    best_k: int | None = None
    best_score = float("-inf")
    best_model: KMeans | None = None

    for k in range(low, high + 1):
        model = KMeans(
            n_clusters=k,
            random_state=seed,
            n_init=20,
            max_iter=500,
            algorithm="lloyd",
        )
        labels = model.fit_predict(prepared.scaled)
        # Silhouette needs at least 2 clusters and samples > k.
        if len(prepared.geoids) <= k:
            score = float("-inf")
        else:
            score = float(silhouette_score(prepared.scaled, labels, random_state=seed))
        candidate_scores[str(k)] = score
        if score > best_score or (
            score == best_score and (best_k is None or k < best_k)
        ):
            best_score = score
            best_k = k
            best_model = model

    assert best_model is not None and best_k is not None
    raw_labels = best_model.labels_.astype(int)
    # Canonical reorder: sort clusters by mean of feature 0 (descending), tie-break by
    # original label ascending.
    order_keys: list[tuple[float, int]] = []
    for label in range(best_k):
        members = prepared.raw[raw_labels == label, 0]
        mean0 = float(members.mean()) if members.size else float("-inf")
        order_keys.append((-mean0, label))
    order_keys.sort()
    old_to_new = {old: new for new, (_, old) in enumerate(order_keys)}
    labels = np.array([old_to_new[int(label)] for label in raw_labels], dtype=int)
    centroids = np.vstack(
        [prepared.scaled[labels == index].mean(axis=0) for index in range(best_k)]
    )

    pca = PCA(n_components=2, random_state=seed)
    pca_coords = pca.fit_transform(prepared.scaled)

    summaries: list[ClusterSummary] = []
    cluster_ids_row: list[str] = []
    for index in range(best_k):
        cluster_id = _canonical_cluster_id(index)
        member_mask = labels == index
        member_raw = prepared.raw[member_mask]
        centroid_features = {
            feature_id: float(member_raw[:, col].mean())
            for col, feature_id in enumerate(prepared.feature_ids)
        }
        # Distinctive: largest absolute z vs global mean on scaled space.
        global_mean = prepared.scaled.mean(axis=0)
        member_mean = prepared.scaled[member_mask].mean(axis=0)
        delta = member_mean - global_mean
        ranked = sorted(
            enumerate(delta),
            key=lambda item: abs(float(item[1])),
            reverse=True,
        )
        high = [
            prepared.feature_ids[i]
            for i, value in ranked
            if value > 0
        ][:3]
        low = [
            prepared.feature_ids[i]
            for i, value in ranked
            if value < 0
        ][:3]
        summaries.append(
            ClusterSummary(
                cluster_id=cluster_id,
                label=_default_label(cluster_id),
                member_count=int(member_mask.sum()),
                centroid_features=centroid_features,
                distinctive_high=high,
                distinctive_low=low,
            )
        )

    for label in labels:
        cluster_ids_row.append(_canonical_cluster_id(int(label)))

    quality = QualityReport(
        k=best_k,
        inertia=float(best_model.inertia_),
        silhouette=float(best_score),
        selection_rule=(
            f"maximize silhouette over k in [{low},{high}] with seed={seed}; "
            "ties prefer smaller k"
        ),
        candidate_scores=candidate_scores,
    )

    return ClusterFit(
        labels=labels,
        cluster_ids=tuple(cluster_ids_row),
        summaries=tuple(summaries),
        quality=quality,
        centroids_scaled=centroids,
        pca_coords=pca_coords,
        pca_components=pca.components_,
        pca_mean=pca.mean_,
    )


def nearest_centroid_label(
    scaled_row: np.ndarray,
    centroids_scaled: np.ndarray,
) -> tuple[int, float]:
    deltas = centroids_scaled - scaled_row
    distances = np.linalg.norm(deltas, axis=1)
    index = int(distances.argmin())
    return index, float(distances[index])


def project_pca(
    scaled_rows: np.ndarray,
    components: np.ndarray,
    mean: np.ndarray,
) -> np.ndarray:
    """Project rows with a frozen PCA (components from the fit universe)."""
    return (scaled_rows - mean) @ components.T
