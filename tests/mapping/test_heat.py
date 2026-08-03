"""Tests for HeatMap abstract base class.

Uses SimpleHeatMap — a minimal concrete subclass with additive accumulation
and linear decay — to test all generic HeatMap behaviour.
"""
import numpy as np
import pytest
from shapely.geometry import LineString, Point, box

from mufasa import BoundingBox, Observation, Location, Map
from mufasa.nodes.mapping import HeatMap

from .conftest import BBOX, CRS, RES, CENTRE_X, CENTRE_Y


# ---------------------------------------------------------------------------
# Concrete stub for testing
# ---------------------------------------------------------------------------

class SimpleHeatMap(HeatMap):
    """Additive accumulator: sums confidence in masked cells, linear decay."""

    def _decay(self, delta_t_s: float) -> None:
        self._data *= max(0.0, 1.0 - 0.01 * delta_t_s)

    def _model_update(self, mask: np.ndarray, confidence: float) -> None:
        self._data[mask] += confidence

    def get_config(self) -> dict:
        return {"decay_s": self.decay_s}


@pytest.fixture
def hm():
    h = SimpleHeatMap(decay_s=100.0)
    h.configure(CRS, BBOX, RES)
    return h


# ---------------------------------------------------------------------------

class TestHeatMapAbstract:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            HeatMap(decay_s=100.0)  # type: ignore[abstract]

    def test_missing_decay_raises(self):
        class N(HeatMap):
            def _model_update(self, mask, confidence): pass
            def get_config(self): return {}
        with pytest.raises(TypeError):
            N(decay_s=100.0)

    def test_missing_model_update_raises(self):
        class N(HeatMap):
            def _decay(self, dt): pass
            def get_config(self): return {}
        with pytest.raises(TypeError):
            N(decay_s=100.0)


class TestHeatMapInit:
    def test_decay_s_stored(self):
        assert SimpleHeatMap(decay_s=60.0).decay_s == 60.0

    def test_zero_decay_raises(self):
        with pytest.raises(ValueError):
            SimpleHeatMap(decay_s=0.0)

    def test_negative_decay_raises(self):
        with pytest.raises(ValueError):
            SimpleHeatMap(decay_s=-1.0)


class TestHeatMapTypes:
    def test_output_type_is_map(self):
        assert SimpleHeatMap(100.0).output_type is Map

    def test_accepts_event(self):
        assert Observation in SimpleHeatMap(100.0).input_types

    def test_does_not_accept_bare_location(self):
        assert Location not in SimpleHeatMap(100.0).input_types

    def test_event_subclass_accepted(self):
        class SubEvent(Observation):
            pass
        assert any(issubclass(SubEvent, t) for t in SimpleHeatMap(100.0).input_types)


class TestHeatMapConfigure:
    def test_data_shape_matches_bbox_and_resolution(self):
        h = SimpleHeatMap(decay_s=100.0)
        h.configure(CRS, BBOX, RES)
        assert h._data.shape == (10, 10)

    def test_data_initialised_to_zeros(self):
        h = SimpleHeatMap(decay_s=100.0)
        h.configure(CRS, BBOX, RES)
        assert np.all(h._data == 0.0)

    def test_transform_set(self):
        h = SimpleHeatMap(decay_s=100.0)
        h.configure(CRS, BBOX, RES)
        assert h._transform is not None

    def test_crs_set(self):
        h = SimpleHeatMap(decay_s=100.0)
        h.configure(CRS, BBOX, RES)
        assert h._crs is not None

    def test_map_before_configure_raises(self):
        with pytest.raises(RuntimeError):
            _ = SimpleHeatMap(decay_s=100.0).map

    def test_process_before_configure_raises(self):
        obs = Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=0.5)
        with pytest.raises(RuntimeError):
            SimpleHeatMap(decay_s=100.0).process(obs)


class TestHeatMapProcess:
    def test_process_returns_map(self, hm, center_event):
        result = hm.process(center_event)
        assert isinstance(result, Map)

    def test_process_updates_cells_under_event(self, hm, center_event):
        hm.process(center_event)
        assert hm._data[5, 5] > 0.0

    def test_cells_outside_event_unaffected_on_first_event(self, hm):
        obs = Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.5)
        hm.process(obs)
        # corner pixel far from centre should be zero (no decay on first Observation from 0)
        assert hm._data[0, 0] == 0.0

    def test_process_updates_map_timestamp(self, hm, center_event):
        hm.process(center_event)
        assert hm.map.timestamp == center_event.timestamp

    def test_map_timestamp_not_decremented_by_older_event(self, hm, center_event):
        hm.process(center_event)
        old_event = Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=0.5)
        hm.process(old_event)
        assert hm.map.timestamp == center_event.timestamp

    def test_map_is_same_object_across_calls(self, hm, center_event):
        m1 = hm.map
        hm.process(center_event)
        m2 = hm.map
        assert m1 is m2

    def test_process_triggers_successors(self, hm, center_event):
        call_count = []

        from mufasa import Node
        class RecordingSink(Node):
            _input_types = [Map]
            _output_type = None
            def process(self): call_count.append(1)
            def get_config(self): return {}

        RecordingSink()(hm)
        hm.process(center_event)
        assert call_count == [1]


class TestHeatMapDecay:
    def test_decay_applied_between_events(self, hm, center_event, later_event):
        hm.process(center_event)
        value_after_first = hm._data[5, 5]
        hm.process(later_event)
        # later_event is at a different pixel, so [5,5] should only have decayed
        assert hm._data[5, 5] < value_after_first

    def test_no_decay_on_zero_time_gap(self, hm, center_event):
        hm.process(center_event)
        value = hm._data[5, 5]
        same_time_event = Observation(
            geometry=Point(500015.0, 5200085.0),
            timestamp=center_event.timestamp,
            confidence=0.5,
        )
        hm.process(same_time_event)
        assert hm._data[5, 5] == value


class TestHeatMapReset:
    def test_reset_clears_data(self, hm, center_event):
        hm.process(center_event)
        hm.reset()
        assert np.all(hm._data == 0.0)

    def test_reset_clears_timestamp(self, hm, center_event):
        hm.process(center_event)
        hm.reset()
        assert hm.map.timestamp == 0.0

    def test_process_works_after_reset(self, hm, center_event):
        hm.process(center_event)
        hm.reset()
        hm.process(center_event)
        assert hm._data[5, 5] > 0.0


class TestHeatMapMask:
    def test_point_inside_bbox_produces_nonzero_mask(self, hm):
        obs = Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert mask.any()

    def test_point_marks_single_pixel_without_radius(self, hm):
        obs = Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert mask.sum() == 1

    def test_point_with_radius_marks_circle_of_pixels(self, hm):
        # radius=15 m at 10 m/px: all 3×3 pixels centred on (row 5, col 5) are
        # within 15 m of the point (max diagonal ~14.1 m < 15 m).
        obs = Observation(
            geometry=Point(CENTRE_X, CENTRE_Y),
            timestamp=1.0, confidence=1.0,
            properties={"radius": 15.0},
        )
        mask = hm._get_mask(obs)
        assert mask.sum() == 9  # 3×3 neighbourhood
        assert mask[5, 5]       # centre pixel set

    def test_point_radius_larger_marks_more_pixels(self, hm):
        small = Observation(
            geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=1.0,
            properties={"radius": 15.0},
        )
        large = Observation(
            geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=1.0,
            properties={"radius": 25.0},
        )
        assert hm._get_mask(large).sum() > hm._get_mask(small).sum()

    def test_point_outside_bbox_produces_zero_mask(self, hm):
        obs = Observation(geometry=Point(0.0, 0.0), timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert not mask.any()

    def test_linestring_without_width_marks_traversed_pixels(self, hm):
        # Horizontal line across the middle of the grid — row 5 only.
        line = LineString([(500010.0, CENTRE_Y), (500090.0, CENTRE_Y)])
        obs = Observation(geometry=line, timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert mask.any()
        # All marked pixels must be in row 5 (bresenham, no width expansion)
        rows, _ = np.where(mask)
        assert set(rows.tolist()) == {5}

    def test_linestring_with_width_marks_corridor(self, hm):
        # width=30 m buffers ±15 m around the line; centroids of rows 4, 5, 6
        # (at y=5200055, 5200045, 5200035) all fall within the 15 m buffer.
        line = LineString([(500010.0, CENTRE_Y), (500090.0, CENTRE_Y)])
        obs = Observation(
            geometry=line, timestamp=1.0, confidence=1.0,
            properties={"width": 30.0},
        )
        mask = hm._get_mask(obs)
        rows, _ = np.where(mask)
        assert set(rows.tolist()) >= {4, 5, 6}

    def test_linestring_width_expands_beyond_no_width(self, hm):
        line = LineString([(500010.0, CENTRE_Y), (500090.0, CENTRE_Y)])
        narrow = Observation(geometry=line, timestamp=1.0, confidence=1.0)
        wide   = Observation(
            geometry=line, timestamp=1.0, confidence=1.0,
            properties={"width": 30.0},
        )
        assert hm._get_mask(wide).sum() > hm._get_mask(narrow).sum()

    def test_polygon_covering_full_bbox_fills_mask(self, hm):
        full_poly = box(500000.0, 5200000.0, 500100.0, 5200100.0)
        obs = Observation(geometry=full_poly, timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert mask.all()

    def test_polygon_larger_than_bbox_fills_all_pixels(self, hm):
        # Polygon that extends well outside the bbox on all sides
        oversized = box(499000.0, 5199000.0, 501000.0, 5201000.0)
        obs = Observation(geometry=oversized, timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert mask.all()

    def test_polygon_partially_outside_bbox_marks_subset(self, hm):
        # Left half of the bbox plus area outside — should mark left half pixels only
        partial = box(499000.0, 5200000.0, 500050.0, 5200100.0)
        obs = Observation(geometry=partial, timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert mask.any()
        assert not mask.all()

    def test_polygon_entirely_outside_bbox_produces_zero_mask(self, hm):
        # Polygon nowhere near the 500000–500100 / 5200000–5200100 grid
        far_away = box(0.0, 0.0, 1.0, 1.0)
        obs = Observation(geometry=far_away, timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert not mask.any()

    def test_polygon_touching_bbox_edge_marks_edge_pixels(self, hm):
        # Strip that covers only the leftmost column area including just the
        # border of the bbox — pixels touching the edge should still be marked.
        edge_strip = box(499990.0, 5200000.0, 500015.0, 5200100.0)
        obs = Observation(geometry=edge_strip, timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert mask.any()

    def test_polygon_ignores_radius_property(self, hm):
        # Polygons are used as-is; a stray 'radius' property must not break anything.
        poly = box(500040.0, 5200040.0, 500060.0, 5200060.0)
        obs = Observation(
            geometry=poly, timestamp=1.0, confidence=1.0,
            properties={"radius": 100.0},
        )
        mask_with    = hm._get_mask(obs)
        event_plain  = Observation(geometry=poly, timestamp=1.0, confidence=1.0)
        mask_without = hm._get_mask(event_plain)
        assert np.array_equal(mask_with, mask_without)

    def test_none_geometry_returns_false_mask(self, hm):
        obs = Observation(geometry=None, timestamp=1.0, confidence=1.0)
        mask = hm._get_mask(obs)
        assert not mask.any()
        assert mask.shape == (10, 10)
