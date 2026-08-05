import pytest
from shapely.geometry import Point
from rasterio.transform import Affine
from rasterio.crs import CRS

from mufasa import Observation, Location, Map
from mufasa.io.inputs.base import InputNode
from mufasa.io.inputs.python_object import LocationInput, MapInput


def make_location(x=0.0, y=0.0):
    return Location(geometry=Point(x, y))


def make_event(timestamp, x=0.0, y=0.0):
    return Observation(geometry=Point(x, y), timestamp=timestamp)


class TestLocationInput:
    def test_is_file_input(self):
        assert issubclass(LocationInput, InputNode)

    def test_empty_collection_raises(self):
        with pytest.raises(ValueError):
            LocationInput([])

    def test_generator_accepted(self):
        node = LocationInput(make_location() for _ in range(3))
        assert len(node.items()) == 3

    def test_load_locations_returns_same_items(self):
        locs = [make_location(float(i), float(i)) for i in range(3)]
        assert LocationInput(locs).items() == locs

    def test_load_events_sorted_by_timestamp(self):
        events = [make_event(3.0), make_event(1.0), make_event(2.0)]
        result = LocationInput(events).items()
        assert [e.timestamp for e in result] == [1.0, 2.0, 3.0]

    def test_load_events_returns_event_objects(self):
        events = [make_event(float(i)) for i in range(3)]
        assert all(isinstance(e, Observation) for e in LocationInput(events).items())

    def test_output_type_is_location(self):
        assert LocationInput([make_location()]).output_type is Location


def make_map(timestamp: float = 0.0):
    transform = Affine(10.0, 0.0, 0.0, 0.0, -10.0, 10_000.0)
    crs = CRS.from_epsg(32633)
    import numpy as np
    return Map(np.zeros((10, 10)), transform, crs, timestamp=timestamp)


class TestMapInput:
    def test_is_file_input(self):
        assert issubclass(MapInput, InputNode)

    def test_empty_collection_raises(self):
        with pytest.raises(ValueError):
            MapInput([])

    def test_non_map_items_raise(self):
        with pytest.raises(TypeError):
            MapInput([make_location()])

    def test_generator_accepted(self):
        node = MapInput(make_map() for _ in range(3))
        assert len(node.items()) == 3

    def test_output_type_is_map(self):
        assert MapInput([make_map()]).output_type is Map

    def test_load_returns_maps_in_order_when_no_timestamps(self):
        maps = [make_map() for _ in range(3)]
        assert MapInput(maps).items() == maps

    def test_load_sorts_by_timestamp(self):
        m1 = make_map(timestamp=3.0)
        m2 = make_map(timestamp=1.0)
        m3 = make_map(timestamp=2.0)
        result = MapInput([m1, m2, m3]).items()
        assert [m.timestamp for m in result] == [1.0, 2.0, 3.0]

    def test_maps_at_zero_timestamp_sorted_before_later(self):
        m_ts = make_map(timestamp=5.0)
        m_no = make_map(timestamp=0.0)
        result = MapInput([m_ts, m_no]).items()
        assert result[0] is m_no
        assert result[1] is m_ts

    def test_get_config_raises(self):
        with pytest.raises(TypeError):
            MapInput([make_map()]).get_config()
