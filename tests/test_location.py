import pytest
from shapely.geometry import LineString, MultiLineString, MultiPoint, Point, Polygon

from mufasa import Observation, Location


class TestLocation:
    def test_requires_geometry(self):
        with pytest.raises(TypeError):
            Location()

    def test_minimal_construction(self, point):
        loc = Location(geometry=point)
        assert loc.geometry == point

    def test_timestamp_defaults_to_zero(self, point):
        loc = Location(geometry=point)
        assert loc.timestamp == 0.0

    def test_timestamp_can_be_set(self, point):
        loc = Location(geometry=point, timestamp=1_700_000_000.0)
        assert loc.timestamp == 1_700_000_000.0

    def test_properties_default_to_empty_dict(self, point):
        loc = Location(geometry=point)
        assert loc.properties == {}

    def test_properties_are_not_shared_between_instances(self):
        a = Location(geometry=Point(0, 0))
        b = Location(geometry=Point(1, 1))
        a.properties["key"] = "value"
        assert "key" not in b.properties

    def test_with_properties(self, point):
        props = {"label": "target", "source": "radar"}
        loc = Location(geometry=point, properties=props)
        assert loc.properties == props

    def test_point_geometry(self, point):
        loc = Location(geometry=point)
        assert loc.geometry.geom_type == "Point"

    def test_linestring_geometry(self):
        line = LineString([(0, 0), (1, 1), (2, 0)])
        loc = Location(geometry=line)
        assert loc.geometry.geom_type == "LineString"

    def test_polygon_geometry(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        loc = Location(geometry=poly)
        assert loc.geometry.geom_type == "Polygon"


class TestObservation:
    def test_is_a_location(self, point):
        e = Observation(geometry=point)
        assert isinstance(e, Location)

    def test_requires_geometry(self):
        with pytest.raises(TypeError):
            Observation()

    def test_default_timestamp_is_zero(self, point):
        e = Observation(geometry=point)
        assert e.timestamp == 0.0

    def test_default_confidence_is_half(self, point):
        e = Observation(geometry=point)
        assert e.confidence == 0.5

    def test_with_all_fields(self, point):
        e = Observation(
            geometry=point,
            timestamp=1_700_000_000.0,
            confidence=0.85,
            properties={"sensor": "camera"},
        )
        assert e.timestamp == 1_700_000_000.0
        assert e.confidence == 0.85
        assert e.properties["sensor"] == "camera"

    def test_inherits_independent_properties(self):
        a = Observation(geometry=Point(0, 0))
        b = Observation(geometry=Point(1, 1))
        a.properties["x"] = 1
        assert "x" not in b.properties

    def test_geometry_accessible_via_location_field(self, point):
        e = Observation(geometry=point)
        assert e.geometry is point


class TestEffectiveGeometry:
    # --- None geometry ---

    def test_none_geometry_returns_none(self):
        loc = Location(geometry=None)
        assert loc.effective_geometry is None

    # --- Point + radius ---

    def test_point_without_radius_returns_same_object(self, point):
        loc = Location(geometry=point)
        assert loc.effective_geometry is point

    def test_point_with_radius_returns_polygon(self):
        loc = Location(geometry=Point(0, 0), properties={"radius": 10.0})
        result = loc.effective_geometry
        assert result.geom_type == "Polygon"

    def test_point_buffered_by_radius(self):
        loc = Location(geometry=Point(0, 0), properties={"radius": 5.0})
        result = loc.effective_geometry
        # buffered area ≈ π r² = ~78.5 m²
        assert abs(result.area - 5.0 ** 2 * 3.14159) < 1.0

    def test_point_radius_zero_is_still_applied(self):
        loc = Location(geometry=Point(0, 0), properties={"radius": 0.0})
        result = loc.effective_geometry
        # buffer(0) → degenerate polygon, but should not raise
        assert result is not None

    def test_multipoint_with_radius_is_buffered(self):
        mp = MultiPoint([(0, 0), (10, 0)])
        loc = Location(geometry=mp, properties={"radius": 3.0})
        result = loc.effective_geometry
        assert result.geom_type in ("Polygon", "MultiPolygon")

    # --- LineString + width ---

    def test_linestring_without_width_returns_same_object(self):
        line = LineString([(0, 0), (10, 0)])
        loc = Location(geometry=line)
        assert loc.effective_geometry is line

    def test_linestring_with_width_returns_polygon(self):
        line = LineString([(0, 0), (10, 0)])
        loc = Location(geometry=line, properties={"width": 4.0})
        result = loc.effective_geometry
        assert result.geom_type == "Polygon"

    def test_linestring_buffered_by_half_width(self):
        line = LineString([(0, 0), (10, 0)])
        loc = Location(geometry=line, properties={"width": 4.0})
        result = loc.effective_geometry
        # Corridor should extend ±2 m perpendicularly from the 10 m line.
        # Width of bounding box in y should be ~4 m.
        minx, miny, maxx, maxy = result.bounds
        assert abs((maxy - miny) - 4.0) < 0.5

    def test_multilinestring_with_width_is_buffered(self):
        ml = MultiLineString([[(0, 0), (5, 0)], [(10, 0), (15, 0)]])
        loc = Location(geometry=ml, properties={"width": 2.0})
        result = loc.effective_geometry
        assert result.geom_type in ("Polygon", "MultiPolygon")

    # --- Other geometry types ---

    def test_polygon_ignores_radius(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        loc = Location(geometry=poly, properties={"radius": 100.0})
        assert loc.effective_geometry is poly

    def test_polygon_ignores_width(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        loc = Location(geometry=poly, properties={"width": 100.0})
        assert loc.effective_geometry is poly

    # --- Observation inherits the property ---

    def test_event_effective_geometry_uses_radius(self):
        e = Observation(geometry=Point(0, 0), timestamp=1.0, confidence=0.9,
                  properties={"radius": 10.0})
        assert e.effective_geometry.geom_type == "Polygon"

    def test_event_without_radius_returns_raw_geometry(self):
        p = Point(0, 0)
        e = Observation(geometry=p, timestamp=1.0, confidence=0.9)
        assert e.effective_geometry is p
