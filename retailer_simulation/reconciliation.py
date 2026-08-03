"""Reconciliation between scenario targets and generated simulation outputs."""

from __future__ import annotations

from retailer_simulation.benchmarks import benchmark_value
from retailer_simulation.models import (
    BenchmarkCatalog,
    MonthlyPerformance,
    ReconciliationLine,
    RetailerScenario,
    SegmentShare,
    SimulatedStore,
)


def _within_tolerance(target: float, generated: float, tolerance_pct: float) -> bool:
    if target == 0:
        return generated == 0
    return abs(generated - target) / abs(target) <= tolerance_pct


def build_reconciliation(
    *,
    scenario: RetailerScenario,
    stores: list[SimulatedStore],
    segments: list[SegmentShare],
    monthly: list[MonthlyPerformance],
    catalog: BenchmarkCatalog,
) -> list[ReconciliationLine]:
    total_sales = sum(store.annual_sales_usd for store in stores)
    avg_store_sales = total_sales / len(stores) if stores else 0.0
    anchor_sales = benchmark_value(catalog, "avg_annual_store_sales_usd")
    margin_values = [store.gross_margin_pct for store in stores]
    min_margin = min(margin_values) if margin_values else 0.0
    max_margin = max(margin_values) if margin_values else 0.0
    segment_total = sum(segment.share_pct for segment in segments)
    monthly_total = sum(entry.total_sales_usd for entry in monthly)
    negative_count = sum(
        1
        for store in stores
        if store.annual_sales_usd < 0 or store.gross_margin_pct < 0 or store.sq_ft < 0
    )

    lines = [
        ReconciliationLine(
            metric="total_annual_sales_usd",
            target=scenario.sales_target_usd,
            generated=round(total_sales, 2),
            tolerance_pct=0.01,
            passed=_within_tolerance(scenario.sales_target_usd, total_sales, 0.01),
            note="Store sales scaled to the explicit scenario sales target.",
        ),
        ReconciliationLine(
            metric="monthly_roll_up_usd",
            target=round(total_sales, 2),
            generated=round(monthly_total, 2),
            tolerance_pct=0.001,
            passed=_within_tolerance(total_sales, monthly_total, 0.001),
            note="Monthly seasonality weights sum to 1.0.",
        ),
        ReconciliationLine(
            metric="avg_store_sales_usd",
            target=anchor_sales,
            generated=round(avg_store_sales, 2),
            tolerance_pct=0.35,
            passed=_within_tolerance(anchor_sales, avg_store_sales, 0.35),
            note="Informational check against the public anchor after scaling.",
        ),
        ReconciliationLine(
            metric="store_count",
            target=float(scenario.store_count),
            generated=float(len(stores)),
            tolerance_pct=0.0,
            passed=len(stores) == scenario.store_count,
            note="Referential integrity: one row per requested store.",
        ),
        ReconciliationLine(
            metric="segment_share_total_pct",
            target=100.0,
            generated=round(segment_total, 4),
            tolerance_pct=0.01,
            passed=_within_tolerance(100.0, segment_total, 0.01),
            note="Customer segment shares must sum to 100%.",
        ),
        ReconciliationLine(
            metric="margin_range_pct",
            target=scenario.margin_max_pct - scenario.margin_min_pct,
            generated=round(max_margin - min_margin, 4),
            tolerance_pct=0.0,
            passed=scenario.margin_min_pct <= min_margin and max_margin <= scenario.margin_max_pct,
            note="All store margins stay inside the scenario range.",
        ),
        ReconciliationLine(
            metric="non_negative_values",
            target=0.0,
            generated=float(negative_count),
            tolerance_pct=0.0,
            passed=negative_count == 0,
            note="No negative sales, margins, or square footage.",
        ),
    ]
    return lines
