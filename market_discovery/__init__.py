"""Public-county market discovery and deterministic archetype clustering.

Analytical membership lives here — never in the TypeScript client. The agent may
request or explain results via ``market.archetype_analysis``; it cannot invent cluster
ids or recompute K-means.
"""

from market_discovery.service import MarketDiscoveryService, get_market_discovery_service

__all__ = [
    "MarketDiscoveryService",
    "get_market_discovery_service",
]
