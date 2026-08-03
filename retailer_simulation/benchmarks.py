"""Load and filter public benchmark anchors."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from models.provenance import DataClass, data_class_view
from retailer_simulation.models import (
    BRAND_NAME,
    Benchmark,
    BenchmarkCatalog,
    VerificationState,
)

DEFAULT_BENCHMARKS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "retailer_simulation" / "public_benchmarks.yaml"
)


class BenchmarkLoadError(RuntimeError):
    pass


def load_benchmark_catalog(path: str | Path | None = None) -> BenchmarkCatalog:
    catalog_path = Path(path) if path else DEFAULT_BENCHMARKS_PATH
    if not catalog_path.is_file():
        raise BenchmarkLoadError(f"Benchmark catalog not found: {catalog_path}")
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    benchmarks: list[Benchmark] = []
    for entry in raw.get("benchmarks", []):
        data_class = DataClass(entry.get("data_class", DataClass.PUBLIC_COMPANY_BENCHMARK))
        benchmarks.append(
            Benchmark(
                metric=entry["metric"],
                value=float(entry["value"]),
                unit=entry["unit"],
                source_name=entry["source_name"],
                source_url=entry.get("source_url"),
                source_period=entry.get("source_period"),
                verification_state=VerificationState(entry["verification_state"]),
                usage=entry["usage"],
                data_class=data_class,
            )
        )
    return BenchmarkCatalog(
        version=str(raw.get("version", "v1")),
        brand=str(raw.get("brand", BRAND_NAME)),
        provenance_notes=list(raw.get("provenance_notes", [])),
        benchmarks=benchmarks,
    )


def active_benchmarks(catalog: BenchmarkCatalog) -> list[Benchmark]:
    """Benchmarks that may influence generation. Disabled entries are excluded."""
    return [
        benchmark
        for benchmark in catalog.benchmarks
        if benchmark.verification_state is not VerificationState.UNVERIFIED_DISABLED
    ]


def benchmark_value(catalog: BenchmarkCatalog, metric: str, *, default: float | None = None) -> float:
    for benchmark in active_benchmarks(catalog):
        if benchmark.metric == metric:
            return benchmark.value
    if default is not None:
        return default
    raise KeyError(metric)


def benchmarks_view(catalog: BenchmarkCatalog) -> dict:
    return {
        "version": catalog.version,
        "brand": catalog.brand,
        "provenance_notes": catalog.provenance_notes,
        "benchmarks": [
            {
                **benchmark.model_dump(mode="json"),
                "data_class": data_class_view(benchmark.data_class),
            }
            for benchmark in catalog.benchmarks
        ],
        "active_count": len(active_benchmarks(catalog)),
        "disabled_count": sum(
            1
            for benchmark in catalog.benchmarks
            if benchmark.verification_state is VerificationState.UNVERIFIED_DISABLED
        ),
        "data_class": data_class_view(DataClass.PUBLIC_COMPANY_BENCHMARK),
    }


@lru_cache(maxsize=1)
def get_benchmark_catalog(path: str | None = None) -> BenchmarkCatalog:
    return load_benchmark_catalog(path)


def clear_benchmark_cache() -> None:
    get_benchmark_catalog.cache_clear()
