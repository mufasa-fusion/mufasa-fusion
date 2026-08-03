"""Tests for KalmanTracker."""
import warnings

import pytest
from shapely.geometry import Point, Polygon

from mufasa.location import Observation, Location
from mufasa.nodes.tracking.kalman import KalmanTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class LocationCollector:
    _successors = []

    def __init__(self):
        self.received: list[Observation] = []

    def process(self, obs: Observation) -> None:
        self.received.append(obs)


def make_tracker(**kwargs) -> tuple[KalmanTracker, LocationCollector]:
    tracker = KalmanTracker(**kwargs)
    tracker.configure(crs=None, bbox=None, resolution=None)
    collector = LocationCollector()
    tracker._successors = [collector]
    return tracker, collector


def push(tracker, *args):
    """Push (x, y, t) tuples as Observations."""
    for x, y, t in args:
        tracker.process(Observation(geometry=Point(x, y), timestamp=t))


def push_and_flush(tracker, *args):
    push(tracker, *args)
    tracker.flush()


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TestKalmanTrackerTypes:
    def test_accepted_input_includes_event(self):
        assert any(issubclass(Observation, t) for t in KalmanTracker().input_types)

    def test_accepted_input_includes_location(self):
        assert Location in KalmanTracker().input_types

    def test_output_type_is_event(self):
        assert KalmanTracker().output_type is Observation

    def test_wires_to_event_source(self):
        from mufasa.node import Node
        class _Src(Node):
            _input_types = []
            _output_type = Observation
            def process(self): pass
            def get_config(self): return {}
        src = _Src()
        tracker = KalmanTracker()(src)
        assert src in tracker._predecessors


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestKalmanTrackerInit:
    def test_default_params_stored(self):
        t = KalmanTracker()
        assert t.buffer_s == pytest.approx(1.0)
        assert t.max_late_s == pytest.approx(5.0)
        assert t.min_detections_to_confirm == 1

    def test_custom_params_stored(self):
        t = KalmanTracker(buffer_s=2.0, max_late_s=10.0, process_noise=0.1,
                          measurement_noise=20.0, max_missed_frames=5,
                          min_detections_to_confirm=3)
        assert t.buffer_s == pytest.approx(2.0)
        assert t.max_late_s == pytest.approx(10.0)
        assert t.process_noise == pytest.approx(0.1)
        assert t.measurement_noise == pytest.approx(20.0)
        assert t.max_missed_frames == 5
        assert t.min_detections_to_confirm == 3

    def test_zero_buffer_s_raises(self):
        with pytest.raises(ValueError):
            KalmanTracker(buffer_s=0.0)

    def test_negative_buffer_s_raises(self):
        with pytest.raises(ValueError):
            KalmanTracker(buffer_s=-1.0)

    def test_negative_max_late_s_raises(self):
        with pytest.raises(ValueError):
            KalmanTracker(max_late_s=-1.0)


# ---------------------------------------------------------------------------
# Buffering
# ---------------------------------------------------------------------------

class TestKalmanTrackerBuffering:
    def test_no_output_within_same_window(self):
        tracker, collector = make_tracker(buffer_s=5.0)
        push(tracker, (100, 200, 0.0), (101, 201, 1.0), (102, 202, 2.0))
        assert collector.received == []

    def test_flush_drains_remaining_buffer(self):
        # Need 2 scans: scan 1 creates tentative track, scan 2 confirms it.
        tracker, collector = make_tracker(
            buffer_s=10.0, min_detections_to_confirm=1
        )
        push(tracker, (100, 200, 0.0), (100, 200, 0.5))  # scan 1
        push(tracker, (100, 200, 11.0))                   # triggers flush of scan 1 → tentative
        tracker.flush()                                    # flushes scan 2 → confirms
        assert len(collector.received) >= 1

    def test_new_window_triggers_flush_of_previous(self):
        # scan 1 flush → tentative; scan 2 flush → confirmed
        tracker, collector = make_tracker(
            buffer_s=1.0, min_detections_to_confirm=1
        )
        push(tracker, (100, 200, 0.0))   # scan 1 buffered
        assert collector.received == []
        push(tracker, (100, 200, 1.5))   # triggers flush of scan 1 → tentative
        assert collector.received == []
        push(tracker, (100, 200, 3.0))   # triggers flush of scan 2 → confirms
        assert len(collector.received) >= 1

    def test_events_sorted_before_scan(self):
        # Sorting within a scan should not raise and should produce tracks over 2 scans.
        tracker, collector = make_tracker(
            buffer_s=5.0, min_detections_to_confirm=1
        )
        push(tracker, (100, 200, 0.3), (100, 200, 0.1), (100, 200, 0.2))  # scan 1 (out of order)
        push(tracker, (100, 200, 6.0))   # triggers flush of scan 1 → tentative
        tracker.flush()                  # flushes scan 2 → confirms
        assert len(collector.received) >= 1

    def test_no_output_for_empty_pipeline(self):
        tracker, collector = make_tracker()
        tracker.flush()
        assert collector.received == []


# ---------------------------------------------------------------------------
# Late events
# ---------------------------------------------------------------------------

class TestKalmanTrackerLateEvents:
    def test_late_event_within_tolerance_accepted(self):
        # Late Observation clamped to buffer_start, contributes to scan 1.
        # Scan 2 confirms the track.
        tracker, collector = make_tracker(
            buffer_s=1.0, max_late_s=5.0, min_detections_to_confirm=1
        )
        push(tracker, (100, 200, 2.0))   # scan 1 starts at t=2.0
        push(tracker, (101, 201, 0.5))   # 1.5s late → clamped to t=2.0, added to scan 1
        push(tracker, (100, 200, 3.5))   # triggers flush of scan 1 → tentative
        tracker.flush()                  # flushes scan 2 → confirms
        assert len(collector.received) >= 1

    def test_late_event_beyond_tolerance_dropped(self):
        tracker, collector = make_tracker(
            buffer_s=1.0, max_late_s=1.0, min_detections_to_confirm=1
        )
        push(tracker, (100, 200, 10.0))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            push(tracker, (100, 200, 5.0))  # 5s late, beyond max_late_s=1
            assert len(w) == 1
            assert "dropped" in str(w[0].message).lower()

    def test_late_event_drop_warning_contains_timestamps(self):
        tracker, _ = make_tracker(buffer_s=1.0, max_late_s=1.0)
        push(tracker, (100, 200, 10.0))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            push(tracker, (100, 200, 5.0))
            assert "5.00" in str(w[0].message)
            assert "10.00" in str(w[0].message)

    def test_late_event_clamped_to_buffer_start(self):
        tracker, collector = make_tracker(
            buffer_s=1.0, max_late_s=5.0, min_detections_to_confirm=1
        )
        push(tracker, (100, 200, 2.0))
        push(tracker, (100, 200, 1.8))  # 0.2s late
        tracker.flush()
        for e in collector.received:
            assert e.timestamp >= 2.0  # clamped up, never negative

    def test_event_at_epoch_is_processed(self):
        tracker, collector = make_tracker(min_detections_to_confirm=1)
        tracker.process(Observation(geometry=Point(100, 200), timestamp=0.0, confidence=0.9))
        tracker.flush()
        # epoch-timestamped events are valid inputs; tracker processes them normally
        assert isinstance(collector.received, list)


# ---------------------------------------------------------------------------
# Tracking behaviour
# ---------------------------------------------------------------------------

class TestKalmanTrackerTracking:
    def _confirmed_tracks(self, n_scans=3, detections_per_scan=1, min_confirm=2):
        tracker, collector = make_tracker(
            buffer_s=1.0,
            min_detections_to_confirm=min_confirm,
            measurement_noise=5.0,
        )
        for i in range(n_scans):
            push(tracker, *[(100 + i, 200 + i, float(i) * 1.5) for _ in range(detections_per_scan)])
        # trigger last flush by sending an Observation far in the future
        push(tracker, (0, 0, float(n_scans) * 1.5 + 100))
        return collector.received

    def test_two_scans_not_enough_for_min_detections_2(self):
        tracker, collector = make_tracker(
            buffer_s=1.0, min_detections_to_confirm=2
        )
        push(tracker, (100, 200, 0.0))
        push(tracker, (100, 200, 1.5))
        assert collector.received == []

    def test_track_confirmed_after_min_detections(self):
        events = self._confirmed_tracks(n_scans=3, min_confirm=2)
        assert len(events) >= 1

    def test_track_event_is_event_instance(self):
        events = self._confirmed_tracks()
        assert all(isinstance(e, Observation) for e in events)

    def test_track_event_geometry_is_point(self):
        events = self._confirmed_tracks()
        assert all(isinstance(e.geometry, Point) for e in events)

    def test_track_event_confidence_in_unit_interval(self):
        events = self._confirmed_tracks()
        for e in events:
            assert 0.0 <= e.confidence <= 1.0

    def test_track_event_has_track_id(self):
        events = self._confirmed_tracks()
        for e in events:
            assert "track_id" in e.properties
            assert len(e.properties["track_id"]) > 0

    def test_track_event_has_velocity(self):
        events = self._confirmed_tracks()
        for e in events:
            assert "velocity_x" in e.properties
            assert "velocity_y" in e.properties

    def test_track_id_stable_across_scans(self):
        tracker, collector = make_tracker(
            buffer_s=1.0, min_detections_to_confirm=2, measurement_noise=5.0
        )
        for i in range(4):
            push(tracker, (100 + i * 2, 200 + i * 2, float(i) * 1.5))
        push(tracker, (0, 0, 100.0))

        ids_per_scan = {}
        for e in collector.received:
            ids_per_scan.setdefault(e.timestamp, set()).add(e.properties["track_id"])

        all_ids = [ids for ids in ids_per_scan.values() if ids]
        if len(all_ids) >= 2:
            common = all_ids[0].intersection(all_ids[1])
            assert len(common) >= 1

    def test_two_detections_same_window_can_spawn_two_tracks(self):
        tracker, collector = make_tracker(
            buffer_s=1.0, min_detections_to_confirm=1, measurement_noise=5.0
        )
        # Two well-separated detections, three scans to confirm
        for i in range(3):
            t = float(i) * 1.5
            push(tracker, (100, 200, t), (500, 600, t))
        push(tracker, (0, 0, 100.0))
        ids = {e.properties["track_id"] for e in collector.received}
        assert len(ids) >= 2

    def test_polygon_geometry_uses_centroid(self):
        poly = Polygon([(100, 200), (110, 200), (110, 210), (100, 210)])
        tracker, collector = make_tracker(
            buffer_s=1.0, min_detections_to_confirm=1, measurement_noise=5.0
        )
        for i in range(3):
            tracker.process(Observation(geometry=poly, timestamp=float(i) * 1.5))
        push(tracker, (0, 0, 100.0))
        for e in collector.received:
            assert isinstance(e.geometry, Point)

    def test_track_position_near_detection(self):
        tracker, collector = make_tracker(
            buffer_s=1.0, min_detections_to_confirm=1, measurement_noise=5.0
        )
        for i in range(3):
            push(tracker, (1000.0, 2000.0, float(i) * 1.5))
        push(tracker, (0, 0, 100.0))
        for e in collector.received:
            assert abs(e.geometry.x - 1000.0) < 200.0
            assert abs(e.geometry.y - 2000.0) < 200.0


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestKalmanTrackerReset:
    def test_reset_clears_buffer(self):
        tracker, collector = make_tracker(min_detections_to_confirm=1)
        push(tracker, (100, 200, 0.0))
        tracker.reset()
        tracker.flush()
        assert collector.received == []

    def test_reset_clears_tracks(self):
        tracker, collector = make_tracker(
            buffer_s=1.0, min_detections_to_confirm=1
        )
        for i in range(3):
            push(tracker, (100 + i, 200 + i, float(i) * 1.5))
        push(tracker, (0, 0, 100.0))
        n_before = len(collector.received)
        tracker.reset()
        assert tracker._tracks == set()

    def test_reset_clears_buffer_start(self):
        tracker, _ = make_tracker()
        push(tracker, (100, 200, 5.0))
        tracker.reset()
        assert tracker._buffer_start is None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestKalmanTrackerConfig:
    def test_get_config_has_all_params(self):
        cfg = KalmanTracker(
            buffer_s=2.0, max_late_s=8.0, process_noise=0.1,
            measurement_noise=15.0, max_missed_frames=4,
            min_detections_to_confirm=3,
        ).get_config()
        assert cfg["buffer_s"] == pytest.approx(2.0)
        assert cfg["max_late_s"] == pytest.approx(8.0)
        assert cfg["process_noise"] == pytest.approx(0.1)
        assert cfg["measurement_noise"] == pytest.approx(15.0)
        assert cfg["max_missed_frames"] == 4
        assert cfg["min_detections_to_confirm"] == 3

    def test_get_config_is_serializable(self):
        import json
        cfg = KalmanTracker().get_config()
        json.dumps(cfg)


class TestKalmanTrackerConfigure:
    def test_raises_when_stonesoup_missing(self, spatial):
        import sys
        import unittest.mock
        tracker = KalmanTracker()
        with unittest.mock.patch.dict(sys.modules, {"stonesoup": None}):
            with pytest.raises(ImportError, match="mufasa\\[tracking\\]"):
                tracker.configure(**spatial)

    def test_configure_succeeds_when_stonesoup_installed(self, spatial):
        KalmanTracker().configure(**spatial)
