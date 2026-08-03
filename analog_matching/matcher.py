"""Deterministic analog-store matching math."""

from __future__ import annotations

import math

import numpy as np

from analog_matching.features import (
    CLUSTER_MATCH_BONUS,
    FEATURE_WEIGHTS,
    FORMAT_MISMATCH_PENALTY,
    MATCHING_FEATURE_IDS,
    MIN_MODERATE_SIMILARITY,
    MIN_PEER_COUNT,
    MIN_STRONG_SIMILARITY,
)
from analog_matching.models import (
    AggregateRange,
    AnalogMatch,
    AnalogSearchResult,
    AnalogyStrength,
    FeatureContribution,
    PerformanceSummary,
)
from market_discovery.artifact import LoadedArtifact
from market_discovery.features import FEATURE_BY_ID
from market_discovery.pipeline import _apply_transform, _impute_column
from models.provenance import DataClass
from retailer_simulation.models import SimulatedStore, SimulationArtifact


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def assign_host_county(store: SimulatedStore, artifact: LoadedArtifact) -> tuple[str, str]:
    """Nearest county centroid by lat/lon; tie-break by GEOID."""
    ranked: list[tuple[float, str, str]] = []
    for county in artifact.counties:
        dist = _haversine_km(store.lat, store.lon, county.lat, county.lon)
        ranked.append((dist, county.geoid, county.name))
    ranked.sort(key=lambda item: (item[0], item[1]))
    _, geoid, name = ranked[0]
    return geoid, name


def _feature_vector(
    artifact: LoadedArtifact,
    geoid: str,
    *,
    z_stats: dict[str, tuple[float, float]],
) -> dict[str, float]:
    county = artifact.county(geoid)
    if county is None:
        raise KeyError(geoid)
    values: dict[str, float] = {}
    for feature_id in MATCHING_FEATURE_IDS:
        raw = county.features.get(feature_id)
        numeric = float("nan") if raw is None else float(raw)
        column = np.array([numeric], dtype=float)
        imputed = _impute_column(column, FEATURE_BY_ID[feature_id].missing_policy)
        transformed = _apply_transform(feature_id, imputed)[0]
        mean, scale = z_stats[feature_id]
        z = 0.0 if scale <= 0 else (transformed - mean) / scale
        values[feature_id] = float(z)
    return values


def _build_z_stats(artifact: LoadedArtifact) -> dict[str, tuple[float, float]]:
    stats: dict[str, tuple[float, float]] = {}
    for feature_id in MATCHING_FEATURE_IDS:
        column_values: list[float] = []
        for county in artifact.counties:
            raw = county.features.get(feature_id)
            numeric = float("nan") if raw is None else float(raw)
            column = np.array([numeric], dtype=float)
            imputed = _impute_column(column, FEATURE_BY_ID[feature_id].missing_policy)
            transformed = _apply_transform(feature_id, imputed)[0]
            column_values.append(float(transformed))
        arr = np.array(column_values, dtype=float)
        mean = float(np.mean(arr))
        scale = float(np.std(arr))
        if scale <= 1e-9:
            scale = 1.0
        stats[feature_id] = (mean, scale)
    return stats


def _raw_feature_value(artifact: LoadedArtifact, geoid: str, feature_id: str) -> float | None:
    county = artifact.county(geoid)
    if county is None:
        return None
    raw = county.features.get(feature_id)
    return None if raw is None else float(raw)


def _distance_and_contributions(
    candidate_z: dict[str, float],
    store_z: dict[str, float],
    *,
    candidate_raw: dict[str, float | None],
    store_raw: dict[str, float | None],
    format_penalty: float,
) -> tuple[float, list[FeatureContribution]]:
    contributions: list[FeatureContribution] = []
    squared = 0.0
    for feature_id in MATCHING_FEATURE_IDS:
        weight = FEATURE_WEIGHTS.get(feature_id, 1.0)
        delta = candidate_z[feature_id] - store_z[feature_id]
        signed = weight * delta
        squared += weight * (delta**2)
        contributions.append(
            FeatureContribution(
                feature_id=feature_id,
                display_name=FEATURE_BY_ID[feature_id].display_name,
                candidate_value=candidate_raw.get(feature_id),
                store_value=store_raw.get(feature_id),
                weight=weight,
                signed_contribution=round(signed, 4),
            )
        )
    distance = math.sqrt(squared) + format_penalty
    contributions.sort(key=lambda item: abs(item.signed_contribution), reverse=True)
    return distance, contributions


def _similarity_from_distance(distance: float) -> float:
    return round(1.0 / (1.0 + distance), 4)


def _performance_summary(stores: list[SimulatedStore]) -> PerformanceSummary:
    sales = np.array([store.annual_sales_usd for store in stores], dtype=float)
    margins = np.array([store.gross_margin_pct for store in stores], dtype=float)
    q25_s, q75_s = float(np.percentile(sales, 25)), float(np.percentile(sales, 75))
    q25_m, q75_m = float(np.percentile(margins, 25)), float(np.percentile(margins, 75))
    return PerformanceSummary(
        median_annual_sales_usd=float(np.median(sales)),
        iqr_annual_sales_usd=(q25_s, q75_s),
        median_gross_margin_pct=float(np.median(margins)),
        iqr_gross_margin_pct=(q25_m, q75_m),
    )


def _analogy_strength(matches: list[AnalogMatch]) -> tuple[AnalogyStrength, list[str]]:
    warnings: list[str] = []
    if not matches:
        return AnalogyStrength.INSUFFICIENT, [
            "No synthetic stores were available to compare against this market profile."
        ]
    top = matches[0].similarity
    if top < MIN_MODERATE_SIMILARITY:
        warnings.append(
            f"Top similarity ({top:.2f}) is below the moderate threshold "
            f"({MIN_MODERATE_SIMILARITY:.2f}). Treat analogs as exploratory only."
        )
        return AnalogyStrength.INSUFFICIENT, warnings
    if len(matches) < MIN_PEER_COUNT:
        warnings.append(
            f"Only {len(matches)} peer(s) returned; at least {MIN_PEER_COUNT} are "
            "recommended before relying on an analog set."
        )
    if top >= MIN_STRONG_SIMILARITY and len(matches) >= MIN_PEER_COUNT:
        return AnalogyStrength.STRONG, warnings
    if top >= MIN_MODERATE_SIMILARITY:
        if top < MIN_STRONG_SIMILARITY:
            warnings.append(
                f"Top similarity ({top:.2f}) is below the strong threshold "
                f"({MIN_STRONG_SIMILARITY:.2f})."
            )
        return AnalogyStrength.MODERATE, warnings
    warnings.append("Peer set is weak; public market features diverge materially.")
    return AnalogyStrength.WEAK, warnings


def search_analogs(
    *,
    artifact: LoadedArtifact,
    candidate_geoid: str,
    candidate_name: str,
    candidate_market_id: str,
    simulation: SimulationArtifact,
    top_k: int = 5,
    preferred_format: str | None = None,
    matcher_version: str,
    feature_set_version: str,
) -> AnalogSearchResult:
    assignment = artifact.assignment(candidate_geoid)
    candidate_cluster = assignment.cluster_id if assignment else ""

    z_stats = _build_z_stats(artifact)
    candidate_z = _feature_vector(artifact, candidate_geoid, z_stats=z_stats)
    candidate_raw = {
        feature_id: _raw_feature_value(artifact, candidate_geoid, feature_id)
        for feature_id in MATCHING_FEATURE_IDS
    }

    scored: list[tuple[float, float, str, AnalogMatch]] = []
    store_by_id = {store.store_id: store for store in simulation.stores}

    for store in simulation.stores:
        host_geoid, host_name = assign_host_county(store, artifact)
        store_z = _feature_vector(artifact, host_geoid, z_stats=z_stats)
        store_raw = {
            feature_id: _raw_feature_value(artifact, host_geoid, feature_id)
            for feature_id in MATCHING_FEATURE_IDS
        }

        mismatches: list[str] = []
        format_penalty = 0.0
        if preferred_format and store.format != preferred_format:
            format_penalty += FORMAT_MISMATCH_PENALTY
            mismatches.append(
                f"Format {store.format!r} differs from preferred {preferred_format!r}."
            )

        host_assignment = artifact.assignment(host_geoid)
        if (
            host_assignment
            and candidate_cluster
            and host_assignment.cluster_id == candidate_cluster
        ):
            format_penalty = max(0.0, format_penalty - CLUSTER_MATCH_BONUS)
        elif host_assignment and candidate_cluster:
            mismatches.append(
                f"Host county archetype {host_assignment.cluster_id} differs from "
                f"candidate {candidate_cluster}."
            )

        distance, contributions = _distance_and_contributions(
            candidate_z,
            store_z,
            candidate_raw=candidate_raw,
            store_raw=store_raw,
            format_penalty=format_penalty,
        )
        similarity = _similarity_from_distance(distance)
        match = AnalogMatch(
            store_id=store.store_id,
            store_name=store.name,
            format=store.format,
            host_geoid=host_geoid,
            host_name=host_name,
            similarity=similarity,
            distance=round(distance, 4),
            contributions=contributions,
            mismatches=mismatches,
            performance_summary=None,
            data_class=DataClass.PUBLIC_MARKET_DATA,
        )
        scored.append((similarity, distance, store.store_id, match))

    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    top_matches = [item[3] for item in scored[:top_k]]

    # Attach simulated performance only after ranking.
    enriched: list[AnalogMatch] = []
    for match in top_matches:
        store = store_by_id[match.store_id]
        perf = _performance_summary([store])
        enriched.append(
            match.model_copy(update={"performance_summary": perf})
        )

    strength, warnings = _analogy_strength(enriched)
    aggregate: AggregateRange | None = None
    if enriched:
        similarities = [entry.similarity for entry in enriched]
        aggregate = AggregateRange(
            min_similarity=min(similarities),
            max_similarity=max(similarities),
            median_similarity=float(np.median(similarities)),
        )

    context_pack = [
        f"Analog search for {candidate_name} (GEOID {candidate_geoid}) using "
        f"{len(simulation.stores)} NorthStar Apparel simulated stores.",
        f"Analogy strength: {strength.value}. Top match: "
        + (
            f"{enriched[0].store_name} (similarity {enriched[0].similarity:.2f})."
            if enriched
            else "none."
        ),
        "Matching uses public ACS county features only; simulated sales and margins "
        "are shown after ranking and labeled simulated_retailer_data.",
    ]
    if warnings:
        context_pack.extend(warnings)

    return AnalogSearchResult(
        candidate_market_id=candidate_market_id,
        candidate_geoid=candidate_geoid,
        candidate_name=candidate_name,
        candidate_cluster_id=candidate_cluster,
        matches=enriched,
        aggregate_range=aggregate,
        analogy_strength=strength,
        warnings=warnings,
        feature_ids=MATCHING_FEATURE_IDS,
        matcher_version=matcher_version,
        feature_set_version=feature_set_version,
        context_pack=context_pack,
    )
