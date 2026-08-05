import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import Affine

from mufasa import BayesianMap, BoundingBox, Map


class TestBoundingBox:
    def test_field_order(self):
        bb = BoundingBox(1.0, 2.0, 3.0, 4.0)
        assert bb.min_x == 1.0
        assert bb.min_y == 2.0
        assert bb.max_x == 3.0
        assert bb.max_y == 4.0

    def test_named_access(self):
        bb = BoundingBox(min_x=10.0, min_y=20.0, max_x=30.0, max_y=40.0)
        assert bb.min_x == 10.0

    def test_is_immutable(self):
        bb = BoundingBox(0.0, 0.0, 1.0, 1.0)
        with pytest.raises(AttributeError):
            bb.min_x = 5.0

    def test_unpacking(self):
        bb = BoundingBox(1.0, 2.0, 3.0, 4.0)
        min_x, min_y, max_x, max_y = bb
        assert (min_x, min_y, max_x, max_y) == (1.0, 2.0, 3.0, 4.0)

    def test_equality(self):
        assert BoundingBox(0, 0, 1, 1) == BoundingBox(0, 0, 1, 1)
        assert BoundingBox(0, 0, 1, 1) != BoundingBox(0, 0, 2, 2)


BOUNDS = BoundingBox(0.0, 0.0, 10_000.0, 10_000.0)
RESOLUTION = (10.0, 10.0)
CRS_STR = "EPSG:32633"


class TestMap:
    def test_is_concrete(self):
        transform = Affine(10.0, 0.0, 0.0, 0.0, -10.0, 10_000.0)
        crs = CRS.from_string(CRS_STR)
        m = Map(np.zeros((10, 10)), transform, crs)
        assert isinstance(m, Map)

    def test_from_bounds_grid_shape(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert m.data.shape == (1000, 1000)

    def test_from_bounds_bbox_roundtrip(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert m.bbox == BOUNDS

    def test_from_bounds_string_crs_converted(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert isinstance(m.crs, CRS)

    def test_from_bounds_crs_object_accepted(self):
        crs = CRS.from_string(CRS_STR)
        m = Map.from_bounds(BOUNDS, RESOLUTION, crs)
        assert m.crs == crs

    def test_from_bounds_data_initialised_to_zeros(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert np.all(m.data == 0.0)

    def test_data_is_mutable(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        m.data[0, 0] = 42.0
        assert m.data[0, 0] == 42.0

    def test_copy_is_independent(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        m.data[0, 0] = 1.0
        c = m.copy()
        c.data[0, 0] = 99.0
        assert m.data[0, 0] == 1.0

    def test_copy_data_matches_original(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        m.data[5, 5] = 7.0
        assert m.copy().data[5, 5] == 7.0

    def test_copy_shares_transform_and_crs(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        c = m.copy()
        assert c.transform == m.transform
        assert c.crs == m.crs

    def test_timestamp_defaults_to_zero(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert m.timestamp == 0.0

    def test_timestamp_can_be_set(self):
        transform = Affine(10.0, 0.0, 0.0, 0.0, -10.0, 10_000.0)
        crs = CRS.from_string(CRS_STR)
        m = Map(np.zeros((10, 10)), transform, crs, timestamp=1_700_000_000.0)
        assert m.timestamp == 1_700_000_000.0

    def test_copy_preserves_timestamp(self):
        transform = Affine(10.0, 0.0, 0.0, 0.0, -10.0, 10_000.0)
        crs = CRS.from_string(CRS_STR)
        m = Map(np.zeros((10, 10)), transform, crs, timestamp=42.0)
        assert m.copy().timestamp == 42.0

    def test_copy_of_map_without_timestamp_has_zero(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert m.copy().timestamp == 0.0


class TestMapWithoutCRS:
    def test_direct_construction_accepts_none_crs(self):
        transform = Affine(10.0, 0.0, 0.0, 0.0, -10.0, 10_000.0)
        m = Map(np.zeros((10, 10)), transform, None)
        assert m.crs is None

    def test_from_bounds_without_crs_argument(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION)
        assert m.crs is None

    def test_from_bounds_explicit_none_crs(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, None)
        assert m.crs is None

    def test_from_bounds_no_crs_has_correct_shape(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION)
        assert m.data.shape == (1000, 1000)

    def test_from_bounds_no_crs_bbox_roundtrip(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION)
        assert m.bbox == BOUNDS

    def test_copy_preserves_none_crs(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION)
        assert m.copy().crs is None

    def test_reproject_raises_when_source_has_no_crs(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION)
        with pytest.raises(ValueError, match="no CRS"):
            m.reproject("EPSG:32633", BOUNDS, RESOLUTION)


class TestBayesianMap:
    def test_is_subclass_of_map(self):
        assert issubclass(BayesianMap, Map)

    def test_can_be_instantiated(self):
        from rasterio.transform import Affine
        from rasterio.crs import CRS
        m = BayesianMap(np.zeros((10, 10)), Affine.identity(), CRS.from_epsg(32633))
        assert isinstance(m, BayesianMap)

    def test_from_bounds_returns_bayesian_map(self):
        m = BayesianMap.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert isinstance(m, BayesianMap)

    def test_copy_preserves_type(self):
        m = BayesianMap.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        m.data[0, 0] = 1.0
        c = m.copy()
        assert isinstance(c, BayesianMap)
        assert c.data[0, 0] == 1.0

    def test_map_copy_does_not_produce_bayesian_map(self):
        m = Map.from_bounds(BOUNDS, RESOLUTION, CRS_STR)
        assert type(m.copy()) is Map
