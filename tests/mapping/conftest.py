"""Shared spatial fixtures for sensor node tests.

All coordinates are in EPSG:32633 (UTM zone 33N, metres).
The bbox covers a 100 m × 100 m area giving a 10 × 10 pixel grid at 10 m/px.

Pixel layout (rasterio convention, origin = top-left):
    col 0 … 9  →  x  500000 … 500090
    row 0 … 9  →  y  5200100 … 5200010

Centre of pixel (row=5, col=5) is at (500055, 5200045).
"""
import pytest
from shapely.geometry import Point

from mufasa import Observation
from tests.helpers import CRS, BBOX, RES, CENTRE_X, CENTRE_Y


@pytest.fixture
def center_event():
    return Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.9)


@pytest.fixture
def later_event():
    """Observation at a different location, 100 s later (= one decay_s=100 half-life)."""
    return Observation(geometry=Point(500015.0, 5200085.0), timestamp=110.0, confidence=0.5)
