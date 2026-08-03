"""Feature matrix preparation for clustering.

Imputation and scaling are fixed policies so membership cannot drift with row order or
ad-hoc notebook transforms. Correlation pruning drops one of each highly correlated pair
using a deterministic feature-id ordering.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from market_discovery.features import (
    CLUSTERING_FEATURE_IDS,
    FEATURE_BY_ID,
    FEATURE_SET_VERSION,
    MissingPolicy,
)
from market_discovery.models import CountyRecord

DEFAULT_CORR_THRESHOLD = 0.92
MODEL_VERSION = "kmeans_zscore_v1"
DEFAULT_SEED = 42
DEFAULT_MIN_POPULATION = 50_000
DEFAULT_K_RANGE = (4, 8)


@dataclass(frozen=True)
class PreparedMatrix:
    geoids: tuple[str, ...]
    feature_ids: tuple[str, ...]
    raw: np.ndarray
    scaled: np.ndarray
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    dropped_correlated: tuple[str, ...]
    config_hash: str


def _apply_transform(feature_id: str, values: np.ndarray) -> np.ndarray:
    transform = FEATURE_BY_ID[feature_id].transform
    if transform == "log1p":
        return np.log1p(np.clip(values, a_min=0, a_max=None))
    if transform == "identity":
        return values
    raise ValueError(f"Unknown transform {transform!r} for {feature_id}")


def _impute_column(values: np.ndarray, policy: MissingPolicy) -> np.ndarray:
    mask = np.isnan(values)
    if not mask.any():
        return values
    if policy is MissingPolicy.DROP_ROW:
        raise ValueError("drop_row imputation is not supported in the matrix builder")
    finite = values[~mask]
    fill = float(np.median(finite)) if finite.size else 0.0
    out = values.copy()
    out[mask] = fill
    return out


def config_hash_for(
    *,
    feature_ids: tuple[str, ...],
    seed: int,
    min_population: int,
    k_range: tuple[int, int],
    corr_threshold: float,
) -> str:
    payload = {
        "feature_set_version": FEATURE_SET_VERSION,
        "model_version": MODEL_VERSION,
        "feature_ids": list(feature_ids),
        "seed": seed,
        "min_population": min_population,
        "k_range": list(k_range),
        "corr_threshold": corr_threshold,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def prepare_matrix(
    counties: list[CountyRecord],
    *,
    feature_ids: tuple[str, ...] = CLUSTERING_FEATURE_IDS,
    seed: int = DEFAULT_SEED,
    min_population: int = DEFAULT_MIN_POPULATION,
    k_range: tuple[int, int] = DEFAULT_K_RANGE,
    corr_threshold: float = DEFAULT_CORR_THRESHOLD,
    universe_only: bool = True,
) -> PreparedMatrix:
    """Build a scaled feature matrix with stable column and row ordering."""
    rows = sorted(counties, key=lambda county: county.geoid)
    if universe_only:
        rows = [
            county
            for county in rows
            if county.in_clustering_universe and county.population >= min_population
        ]
    if len(rows) < k_range[1]:
        raise ValueError(
            f"Need at least {k_range[1]} counties for k-range {k_range}; got {len(rows)}"
        )

    frame = pd.DataFrame(
        [
            {feature_id: county.features.get(feature_id) for feature_id in feature_ids}
            | {"geoid": county.geoid}
            for county in rows
        ]
    ).set_index("geoid")
    frame = frame.sort_index()

    kept: list[str] = []
    columns: list[np.ndarray] = []
    for feature_id in feature_ids:
        policy = FEATURE_BY_ID[feature_id].missing_policy
        raw = frame[feature_id].astype(float).to_numpy()
        imputed = _impute_column(raw, policy)
        transformed = _apply_transform(feature_id, imputed)
        kept.append(feature_id)
        columns.append(transformed)

    matrix = np.column_stack(columns)
    # Correlation control: among pairs above threshold, drop the later feature_id.
    corr = np.corrcoef(matrix, rowvar=False)
    drop: set[str] = set()
    for i, left in enumerate(kept):
        if left in drop:
            continue
        for j in range(i + 1, len(kept)):
            right = kept[j]
            if right in drop:
                continue
            if abs(float(corr[i, j])) >= corr_threshold:
                drop.add(right)

    retained = tuple(feature_id for feature_id in kept if feature_id not in drop)
    retain_idx = [kept.index(feature_id) for feature_id in retained]
    raw_retained = matrix[:, retain_idx]

    scaler = StandardScaler()
    scaled = scaler.fit_transform(raw_retained)

    return PreparedMatrix(
        geoids=tuple(frame.index.tolist()),
        feature_ids=retained,
        raw=raw_retained,
        scaled=scaled,
        scaler_mean=tuple(float(value) for value in scaler.mean_),
        scaler_scale=tuple(float(value) for value in scaler.scale_),
        dropped_correlated=tuple(sorted(drop)),
        config_hash=config_hash_for(
            feature_ids=retained,
            seed=seed,
            min_population=min_population,
            k_range=k_range,
            corr_threshold=corr_threshold,
        ),
    )


def scale_rows(
    prepared: PreparedMatrix,
    raw_rows: np.ndarray,
) -> np.ndarray:
    """Apply the frozen scaler to additional rows (post-hoc assignments)."""
    mean = np.asarray(prepared.scaler_mean, dtype=float)
    scale = np.asarray(prepared.scaler_scale, dtype=float)
    scale = np.where(scale == 0, 1.0, scale)
    return (raw_rows - mean) / scale
