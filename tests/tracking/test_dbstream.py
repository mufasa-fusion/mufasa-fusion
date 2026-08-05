"""Tests for DBSTREAMClusterer."""
import pytest
from shapely.geometry import Point, Polygon

from mufasa.location import Observation, Location
from mufasa.nodes.tracking.dbstream import DBSTREAMClusterer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class LocationCollector:
    _successors = []

    def __init__(self):
        self.received: list[Location] = []

    def process(self, obs: Location) -> None:
        self.received.append(obs)


def make_clusterer(**kwargs) -> tuple[DBSTREAMClusterer, LocationCollector]:
    clusterer = DBSTREAMClusterer(**kwargs)
    clusterer.configure(crs=None, bbox=None, resolution=None)
    collector = LocationCollector()
    clusterer._successors = [collector]
    return clusterer, collector


def push(clusterer, *args):
    for x, y, t in args:
        clusterer.process(Location(geometry=Point(x, y), timestamp=t))


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TestDBSTREAMClustererTypes:
    def test_accepted_input_includes_observation(self):
        assert any(issubclass(Observation, t) for t in DBSTREAMClusterer().input_types)

    def test_accepted_input_includes_location(self):
        assert Location in DBSTREAMClusterer().input_types

    def test_output_type_is_location(self):
        assert DBSTREAMClusterer().output_type is Location


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestDBSTREAMClustererInit:
    def test_default_params_stored(self):
        c = DBSTREAMClusterer()
        assert c.timeout_s == pytest.approx(1.0)
        assert c.clustering_threshold == pytest.approx(50.0)

    def test_custom_params_stored(self):
        c = DBSTREAMClusterer(
            timeout_s=2.0, clustering_threshold=30.0,
            fading_factor=0.05, cleanup_interval=8,
            intersection_factor=0.5, minimum_weight=2.0,
        )
        assert c.timeout_s == pytest.approx(2.0)
        assert c.clustering_threshold == pytest.approx(30.0)
        assert c.fading_factor == pytest.approx(0.05)
        assert c.minimum_weight == pytest.approx(2.0)

    def test_zero_timeout_s_raises(self):
        with pytest.raises(ValueError):
            DBSTREAMClusterer(timeout_s=0.0)

    def test_negative_timeout_s_raises(self):
        with pytest.raises(ValueError):
            DBSTREAMClusterer(timeout_s=-1.0)

    def test_zero_clustering_threshold_raises(self):
        with pytest.raises(ValueError):
            DBSTREAMClusterer(clustering_threshold=0.0)

    def test_negative_clustering_threshold_raises(self):
        with pytest.raises(ValueError):
            DBSTREAMClusterer(clustering_threshold=-10.0)


# ---------------------------------------------------------------------------
# Buffering
# ---------------------------------------------------------------------------

class TestDBSTREAMClustererBuffering:
    def test_no_output_within_same_window(self):
        clusterer, collector = make_clusterer(timeout_s=5.0)
        push(clusterer, (100, 200, 0.0), (101, 201, 1.0))
        assert collector.received == []

    def test_flush_drains_buffer(self):
        clusterer, collector = make_clusterer(
            timeout_s=5.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 0.0), (101, 201, 0.5))
        clusterer.flush()
        assert len(collector.received) >= 1

    def test_new_window_triggers_flush(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 0.0))
        assert collector.received == []
        push(clusterer, (100, 200, 1.5))
        assert len(collector.received) >= 1

    def test_empty_flush_emits_nothing(self):
        clusterer, collector = make_clusterer()
        clusterer.flush()
        assert collector.received == []

    def test_location_at_epoch_buffered(self):
        # Locations at t=0 (epoch) are buffered and processed on next flush.
        clusterer, collector = make_clusterer(clustering_threshold=20.0)
        push(clusterer, (100, 200, 1.0))
        clusterer.process(Location(geometry=Point(100, 200), timestamp=0.0))
        clusterer.flush()
        assert len(collector.received) >= 1

    def test_location_at_epoch_before_any_window_buffered(self):
        # Epoch location with no window yet: stays in buffer, contributes on flush.
        clusterer, collector = make_clusterer(clustering_threshold=20.0)
        clusterer.process(Location(geometry=Point(100, 200), timestamp=0.0))
        push(clusterer, (100, 200, 1.0))
        clusterer.flush()
        assert len(collector.received) >= 1


# ---------------------------------------------------------------------------
# Late events
# ---------------------------------------------------------------------------

class TestDBSTREAMClustererLateEvents:
    def test_late_event_clamped_and_accepted(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 10.0))
        push(clusterer, (100, 200, 0.5))  # very late — clamped, not dropped
        clusterer.flush()
        assert len(collector.received) >= 1

    def test_late_event_timestamp_clamped_to_window_start(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 5.0))   # window starts at t=5
        push(clusterer, (100, 200, 3.0))   # late — clamped to t=5
        clusterer.flush()
        for e in collector.received:
            assert e.timestamp >= 5.0


# ---------------------------------------------------------------------------
# Clustering behaviour
# ---------------------------------------------------------------------------

class TestDBSTREAMClustererClustering:
    def test_output_locations_are_location_instances(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 0.0), (100, 200, 1.5))
        clusterer.flush()
        assert all(isinstance(e, Location) for e in collector.received)

    def test_output_geometry_is_point(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 0.0), (100, 200, 1.5))
        clusterer.flush()
        assert all(isinstance(e.geometry, Point) for e in collector.received)

    def test_cluster_event_has_cluster_id(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 0.0), (100, 200, 1.5))
        clusterer.flush()
        for e in collector.received:
            assert "cluster_id" in e.properties

    def test_two_tight_groups_produce_two_clusters(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        for i in range(4):
            t = float(i) * 1.5
            push(clusterer, (100, 200, t), (500, 600, t))
        push(clusterer, (100, 200, 100.0))

        ids = {e.properties["cluster_id"] for e in collector.received}
        assert len(ids) >= 2

    def test_cluster_centre_near_detection_group(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        for i in range(4):
            push(clusterer, (1000.0, 2000.0, float(i) * 1.5))
        push(clusterer, (1000.0, 2000.0, 100.0))

        assert len(collector.received) >= 1
        last = collector.received[-1]
        assert abs(last.geometry.x - 1000.0) < 50.0
        assert abs(last.geometry.y - 2000.0) < 50.0

    def test_cluster_id_stable_across_flushes(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        for i in range(5):
            push(clusterer, (100, 200, float(i) * 1.5))
        push(clusterer, (100, 200, 100.0))

        ids_per_flush = {}
        for e in collector.received:
            ids_per_flush.setdefault(e.timestamp, set()).add(e.properties["cluster_id"])

        per_flush = [s for s in ids_per_flush.values() if s]
        if len(per_flush) >= 2:
            assert per_flush[0] & per_flush[1]  # at least one ID in common

    def test_polygon_geometry_uses_centroid(self):
        poly = Polygon([(100, 200), (110, 200), (110, 210), (100, 210)])
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=50.0
        )
        for i in range(3):
            clusterer.process(Location(geometry=poly, timestamp=float(i) * 1.5))
        push(clusterer, (105, 205, 100.0))
        assert all(isinstance(e.geometry, Point) for e in collector.received)

    def test_model_persists_across_flushes(self):
        clusterer, collector = make_clusterer(
            timeout_s=1.0, clustering_threshold=20.0
        )
        push(clusterer, (100, 200, 0.0))
        push(clusterer, (100, 200, 1.5))   # triggers flush 1 → model fitted
        push(clusterer, (100, 200, 100.0)) # triggers flush 2 → same model
        clusterer.flush()
        assert clusterer._model is not None


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestDBSTREAMClustererReset:
    def test_reset_clears_buffer(self):
        clusterer, collector = make_clusterer(clustering_threshold=20.0)
        push(clusterer, (100, 200, 0.0))
        clusterer.reset()
        clusterer.flush()
        assert collector.received == []

    def test_reset_clears_model(self):
        clusterer, _ = make_clusterer(clustering_threshold=20.0)
        push(clusterer, (100, 200, 0.0), (100, 200, 1.5))
        clusterer.reset()
        assert clusterer._model is None

    def test_reset_clears_timeout_start(self):
        clusterer, _ = make_clusterer()
        push(clusterer, (100, 200, 5.0))
        clusterer.reset()
        assert clusterer._timeout_start is None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestDBSTREAMClustererConfig:
    def test_get_config_has_all_params(self):
        cfg = DBSTREAMClusterer(
            timeout_s=2.0, clustering_threshold=30.0,
            fading_factor=0.05, cleanup_interval=8,
            intersection_factor=0.5, minimum_weight=2.0,
        ).get_config()
        assert cfg["timeout_s"] == pytest.approx(2.0)
        assert cfg["clustering_threshold"] == pytest.approx(30.0)
        assert cfg["fading_factor"] == pytest.approx(0.05)
        assert cfg["cleanup_interval"] == 8
        assert cfg["intersection_factor"] == pytest.approx(0.5)
        assert cfg["minimum_weight"] == pytest.approx(2.0)

    def test_get_config_is_serializable(self):
        import json
        json.dumps(DBSTREAMClusterer().get_config())


class TestDBSTREAMClustererConfigure:
    def test_raises_when_river_missing(self, spatial):
        import sys
        import unittest.mock
        clusterer = DBSTREAMClusterer()
        with unittest.mock.patch.dict(sys.modules, {"river": None}):
            with pytest.raises(ImportError, match="mufasa\\[tracking\\]"):
                clusterer.configure(**spatial)

    def test_configure_succeeds_when_river_installed(self, spatial):
        DBSTREAMClusterer().configure(**spatial)
