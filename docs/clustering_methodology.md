# Clustering methodology

## Universe

- Geography: U.S. counties
- Fit floor: population ≥ 50,000 (configurable at build time)
- Counties below the floor are kept for lookup and assigned by **nearest centroid** after
  the fit (`assignment_method: nearest_centroid`)

## Pipeline

1. Sort counties by GEOID (row-order independence)
2. Median-impute missing values per feature policy
3. Apply registered transforms (`log1p` or `identity`)
4. Drop one feature from each highly correlated pair (|r| ≥ 0.92), preferring earlier
   feature ids
5. Z-score scale (`StandardScaler`)
6. K-means for each k ∈ [4, 8], `random_state=42`, `n_init=20`, Lloyd
7. Select k by maximum silhouette (ties → smaller k)
8. Canonicalize labels: reorder clusters by descending mean of the first retained feature,
   then assign `A01`…`A0k`
9. (Optional presentation) Fit 2-D PCA for methodology tooling; the product UI leads with
   K-means **centroid formulations** (per-feature cluster averages), not a PCA scatter

## Determinism

Same artifact + same seed ⇒ identical membership. Shuffling input counties before
`prepare_matrix` does not change assignments because rows are re-sorted by GEOID.

## What this is not

- Not a store-performance model
- Not a trade-area or drive-time model
- Not Atlas evidence (separate `DataClass`)
- Labels default to `Archetype 0N`; any future LLM rename must not alter membership

## Quality disclosure

Silhouette and inertia are stored on the artifact and shown in the UI. Silhouette is one
of several possible criteria; it is documented so reviewers do not over-interpret a single
score.
