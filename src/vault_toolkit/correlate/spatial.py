"""Spatial correlation analysis."""

import math
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, query_to_polars


def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Calculate the great-circle distance between two points.

    Args:
        lat1, lon1: First point coordinates in degrees.
        lat2, lon2: Second point coordinates in degrees.

    Returns:
        Distance in meters.
    """
    R = 6371000  # Earth's radius in meters

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) *
        math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def correlate_spatial(
    db_path: str,
    source_table: str,
    target_table: str,
    *,
    source_lat: str = "latitude",
    source_lon: str = "longitude",
    target_lat: str = "latitude",
    target_lon: str = "longitude",
    threshold_meters: float = 1000,
    score_weight: float = 1.0,
) -> pl.DataFrame:
    """Find spatial correlations between two tables.

    Args:
        db_path: Path to DuckDB database.
        source_table: Source table name.
        target_table: Target table name.
        source_lat, source_lon: Coordinate columns in source table.
        target_lat, target_lon: Coordinate columns in target table.
        threshold_meters: Maximum distance for correlation.
        score_weight: Weight multiplier for correlation scores.

    Returns:
        DataFrame with correlation results.
    """
    with connect(db_path) as conn:
        # DuckDB supports spatial functions, use haversine formula
        # Convert to radians and calculate distance
        sql = f"""
            WITH distances AS (
                SELECT
                    s.rowid as source_row,
                    t.rowid as target_row,
                    s.{source_lat} as source_lat,
                    s.{source_lon} as source_lon,
                    t.{target_lat} as target_lat,
                    t.{target_lon} as target_lon,
                    6371000 * 2 * ASIN(SQRT(
                        POWER(SIN(RADIANS(t.{target_lat} - s.{source_lat}) / 2), 2) +
                        COS(RADIANS(s.{source_lat})) * COS(RADIANS(t.{target_lat})) *
                        POWER(SIN(RADIANS(t.{target_lon} - s.{source_lon}) / 2), 2)
                    )) as distance_meters
                FROM {source_table} s
                CROSS JOIN {target_table} t
                WHERE s.{source_lat} IS NOT NULL
                  AND s.{source_lon} IS NOT NULL
                  AND t.{target_lat} IS NOT NULL
                  AND t.{target_lon} IS NOT NULL
            )
            SELECT
                source_row,
                target_row,
                source_lat,
                source_lon,
                target_lat,
                target_lon,
                distance_meters,
                {score_weight} * (1.0 - (distance_meters / {threshold_meters})) as score,
                '{source_table}' as source_table,
                '{target_table}' as target_table,
                'spatial' as correlation_type
            FROM distances
            WHERE distance_meters <= {threshold_meters}
            ORDER BY score DESC
        """

        return query_to_polars(conn, sql)


def find_spatial_clusters(
    db_path: str,
    table: str,
    *,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    cluster_threshold_meters: float = 500,
    min_points: int = 3,
) -> pl.DataFrame:
    """Find spatial clusters of points.

    Simple density-based clustering using distance threshold.

    Args:
        db_path: Path to DuckDB database.
        table: Table with coordinate data.
        lat_col: Latitude column name.
        lon_col: Longitude column name.
        cluster_threshold_meters: Distance threshold for clustering.
        min_points: Minimum points to form a cluster.

    Returns:
        DataFrame with cluster assignments.
    """
    with connect(db_path) as conn:
        # Get all points
        points = query_to_polars(
            conn,
            f"SELECT rowid, {lat_col} as lat, {lon_col} as lon FROM {table} WHERE {lat_col} IS NOT NULL AND {lon_col} IS NOT NULL"
        )

        if points.is_empty() or len(points) < min_points:
            return pl.DataFrame(schema={
                "rowid": pl.Int64,
                "cluster_id": pl.Int64,
                "cluster_size": pl.Int64,
            })

        # Simple clustering: assign each point to its nearest cluster or create new
        points_list = points.to_dicts()
        clusters: list[list[dict]] = []

        for point in points_list:
            assigned = False
            for i, cluster in enumerate(clusters):
                # Check if point is within threshold of any cluster member
                for member in cluster:
                    dist = haversine_distance(
                        point["lat"], point["lon"],
                        member["lat"], member["lon"]
                    )
                    if dist <= cluster_threshold_meters:
                        cluster.append(point)
                        assigned = True
                        break
                if assigned:
                    break

            if not assigned:
                clusters.append([point])

        # Build result
        results = []
        cluster_id = 0
        for cluster in clusters:
            if len(cluster) >= min_points:
                for point in cluster:
                    results.append({
                        "rowid": point["rowid"],
                        "cluster_id": cluster_id,
                        "cluster_size": len(cluster),
                    })
                cluster_id += 1

        if not results:
            return pl.DataFrame(schema={
                "rowid": pl.Int64,
                "cluster_id": pl.Int64,
                "cluster_size": pl.Int64,
            })

        return pl.DataFrame(results)


def find_nearby_entities(
    conn: Any,
    lat: float,
    lon: float,
    table: str,
    *,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    radius_meters: float = 1000,
    limit: int = 100,
) -> pl.DataFrame:
    """Find entities within a radius of a point.

    Args:
        conn: DuckDB connection.
        lat, lon: Center point coordinates.
        table: Table to search.
        lat_col, lon_col: Coordinate column names.
        radius_meters: Search radius.
        limit: Maximum results.

    Returns:
        DataFrame with nearby entities and distances.
    """
    sql = f"""
        SELECT
            *,
            6371000 * 2 * ASIN(SQRT(
                POWER(SIN(RADIANS({lat_col} - {lat}) / 2), 2) +
                COS(RADIANS({lat})) * COS(RADIANS({lat_col})) *
                POWER(SIN(RADIANS({lon_col} - {lon}) / 2), 2)
            )) as distance_meters
        FROM {table}
        WHERE {lat_col} IS NOT NULL AND {lon_col} IS NOT NULL
        HAVING distance_meters <= {radius_meters}
        ORDER BY distance_meters
        LIMIT {limit}
    """

    return query_to_polars(conn, sql)
