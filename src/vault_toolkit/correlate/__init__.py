"""Correlation analysis module."""

from vault_toolkit.correlate.temporal import (
    correlate_temporal,
    find_temporal_proximity,
)
from vault_toolkit.correlate.spatial import (
    correlate_spatial,
    haversine_distance,
)
from vault_toolkit.correlate.rules import (
    run_correlation_rules,
    load_rules,
)

__all__ = [
    "correlate_temporal",
    "find_temporal_proximity",
    "correlate_spatial",
    "haversine_distance",
    "run_correlation_rules",
    "load_rules",
]
