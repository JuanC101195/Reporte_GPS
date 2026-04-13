"""Geographic utilities shared across the pipeline."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

import numpy as np

EARTH_RADIUS_M = 6_371_000.0


def haversine_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in meters."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def haversine_matrix(lat_a, lon_a, lat_b, lon_b) -> np.ndarray:
    """Pairwise great-circle distances in meters.

    Returns an ``(|a|, |b|)`` matrix. Inputs are coerced to numpy arrays.
    """
    lat_a = np.radians(np.asarray(lat_a, dtype=float))
    lon_a = np.radians(np.asarray(lon_a, dtype=float))
    lat_b = np.radians(np.asarray(lat_b, dtype=float))
    lon_b = np.radians(np.asarray(lon_b, dtype=float))

    dlat = lat_a[:, None] - lat_b[None, :]
    dlon = lon_a[:, None] - lon_b[None, :]
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat_a)[:, None] * np.cos(lat_b)[None, :] * np.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
