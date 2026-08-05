"""Minimal concrete Node stubs used across all tests."""
import pytest
from shapely.geometry import Point

from mufasa import BoundingBox, Observation, Location, Map, Node
from mufasa.io.inputs.base import InputNode
from mufasa.io.outputs.base import OutputNode


# ---------------------------------------------------------------------------
# Node stubs — named by their type signature (input → output)
# ---------------------------------------------------------------------------

class LocSource(InputNode):
    """Source node: no inputs, outputs Location."""
    _input_types = []
    _output_type = Location

    def items(self): return []
    def get_config(self): return {}


class MapSource(InputNode):
    """Source node: no inputs, outputs Map."""
    _input_types = []
    _output_type = Map

    def items(self): return []
    def get_config(self): return {}


class LocToMap(Node):
    """Processing node: accepts Location, outputs Map."""
    _input_types = [Location]
    _output_type = Map

    def process(self, obs=None): pass
    def get_config(self): return {}


class MapToMap(Node):
    """Processing node: accepts Map, outputs Map."""
    _input_types = [Map]
    _output_type = Map

    def process(self): pass
    def get_config(self): return {}


class MapToLoc(Node):
    """Processing node: accepts Map, outputs Location."""
    _input_types = [Map]
    _output_type = Location

    def process(self): pass
    def get_config(self): return {}


class LocToLoc(Node):
    """Processing node: accepts Location, outputs Location."""
    _input_types = [Location]
    _output_type = Location

    def process(self, obs=None): pass
    def get_config(self): return {}


class MixedToLoc(Node):
    """Processing node: accepts Location or Map, outputs Location."""
    _input_types = [Location, Map]
    _output_type = Location

    def process(self, obs=None): pass
    def get_config(self): return {}


class LocSink(OutputNode):
    """Sink node: accepts Location, no output."""
    _input_types = [Location]
    _output_type = None

    def process(self, obs=None): pass
    def get_config(self): return {}


class MapSink(OutputNode):
    """Sink node: accepts Map, no output."""
    _input_types = [Map]
    _output_type = None

    def process(self): pass
    def get_config(self): return {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def point():
    return Point(10.0, 48.0)


@pytest.fixture
def spatial():
    """Default spatial keyword arguments for Graph construction.

    bbox is in WGS84 (lon, lat). Graph projects it to the target CRS internally.
    """
    return dict(
        crs="EPSG:32633",
        bbox=BoundingBox(14.0, 47.0, 14.1, 47.1),
        resolution=(10.0, 10.0),
    )
