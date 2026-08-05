"""Spatial constants and shared fixtures for detection tests."""
import numpy as np
import pytest
from rasterio.crs import CRS as RasterioCRS
from rasterio.transform import from_bounds
from shapely.geometry import Point

from mufasa import Map, Observation
from mufasa.node import Node
from mufasa.nodes.mapping import POM
from tests.helpers import CRS, BBOX, RES, CENTRE_X, CENTRE_Y


@pytest.fixture
def pom():
    p = POM(decay_s=100.0)
    p.configure(CRS, BBOX, RES)
    return p


@pytest.fixture
def center_event():
    return Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.9)


@pytest.fixture
def pom_with_event(pom, center_event):
    pom.process(center_event)
    return pom


class _MapNode(Node):
    """Minimal predecessor stub exposing a plain Map."""
    _input_types = []
    _output_type = Map

    def __init__(self, m: Map):
        super().__init__()
        self._map = m
        self._map.timestamp = 10.0

    @property
    def map(self) -> Map:
        return self._map

    def process(self): pass
    def get_config(self): return {}


@pytest.fixture
def plain_map_node():
    """A 10×10 plain Map with values in [0, 1]; centre pixel set to 0.9."""
    transform = from_bounds(
        BBOX.min_x, BBOX.min_y, BBOX.max_x, BBOX.max_y,
        10, 10,
    )
    data = np.zeros((10, 10), dtype=np.float64)
    data[5, 5] = 0.9
    m = Map(data, transform, RasterioCRS.from_string(CRS))
    return _MapNode(m)
