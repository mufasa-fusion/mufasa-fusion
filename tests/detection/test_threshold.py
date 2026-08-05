"""Tests for Threshold — type resolved at wiring time."""
import numpy as np
import pytest
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from mufasa import BayesianMap, Map, Observation, Location
from mufasa.nodes.detection import Threshold

from .conftest import BBOX, CENTRE_X, CENTRE_Y, CRS, RES


# ---------------------------------------------------------------------------
# Type resolution at wiring time
# ---------------------------------------------------------------------------

class TestThresholdTypeResolution:
    def test_output_type_none_before_wiring(self):
        assert Threshold(0.5).output_type is None

    def test_wired_to_bayesian_map_output_type_is_observation(self, pom):
        td = Threshold(0.7)(pom)
        assert td.output_type is Observation

    def test_wired_to_bayesian_map_input_types_restricted(self, pom):
        td = Threshold(0.7)(pom)
        assert BayesianMap in td.input_types
        assert Map not in td.input_types

    def test_wired_to_plain_map_output_type_is_location(self, plain_map_node):
        td = Threshold(0.7)(plain_map_node)
        assert td.output_type is Location

    def test_wired_to_plain_map_input_types_is_map(self, plain_map_node):
        td = Threshold(0.7)(plain_map_node)
        assert Map in td.input_types

    def test_invalid_predecessor_type_raises(self, pom):
        td = Threshold(0.7)(pom)
        with pytest.raises(TypeError):
            Threshold(0.7)(td)

    def test_threshold_out_of_range_raises_at_wiring_for_bayesian(self, pom):
        with pytest.raises(ValueError):
            Threshold(1.5)(pom)

    def test_threshold_zero_raises_at_wiring_for_bayesian(self, pom):
        with pytest.raises(ValueError):
            Threshold(0.0)(pom)

    def test_threshold_one_raises_at_wiring_for_bayesian(self, pom):
        with pytest.raises(ValueError):
            Threshold(1.0)(pom)

    def test_out_of_range_threshold_accepted_for_plain_map(self, plain_map_node):
        td = Threshold(1.5)(plain_map_node)
        assert td.output_type is Location


# ---------------------------------------------------------------------------
# Construction validation (before wiring)
# ---------------------------------------------------------------------------

class TestThresholdInit:
    def test_threshold_stored(self):
        assert Threshold(0.5).threshold == pytest.approx(0.5)

    def test_negative_alarm_timeout_raises(self):
        with pytest.raises(ValueError):
            Threshold(0.5, alarm_timeout_s=-1.0)

    def test_negative_dilation_px_raises(self):
        with pytest.raises(ValueError):
            Threshold(0.5, dilation_px=-1)

    def test_float_dilation_px_raises(self):
        with pytest.raises(ValueError):
            Threshold(0.5, dilation_px=1.5)

    def test_negative_simplify_m_raises(self):
        with pytest.raises(ValueError):
            Threshold(0.5, simplify_m=-1.0)


# ---------------------------------------------------------------------------
# Plain Map detection (Location output)
# ---------------------------------------------------------------------------

class TestThresholdPlainMapDetection:
    def test_emits_location(self, plain_map_node):
        td = Threshold(0.7)(plain_map_node)
        results = td.process()
        assert len(results) == 1
        assert isinstance(results[0], Location)
        assert not isinstance(results[0], Observation)

    def test_location_has_mean_value_property(self, plain_map_node):
        td = Threshold(0.7)(plain_map_node)
        loc = td.process()[0]
        assert "mean_value" in loc.properties

    def test_mean_value_above_threshold(self, plain_map_node):
        td = Threshold(0.7)(plain_map_node)
        loc = td.process()[0]
        assert loc.properties["mean_value"] >= 0.7

    def test_location_has_timestamp(self, plain_map_node):
        td = Threshold(0.7)(plain_map_node)
        loc = td.process()[0]
        assert loc.timestamp == pytest.approx(10.0)

    def test_location_geometry_is_polygon(self, plain_map_node):
        from shapely.geometry import Polygon, MultiPolygon
        td = Threshold(0.7)(plain_map_node)
        loc = td.process()[0]
        assert isinstance(loc.geometry, (Polygon, MultiPolygon))

    def test_no_detection_below_threshold(self, plain_map_node):
        td = Threshold(0.95)(plain_map_node)
        assert td.process() == []


# ---------------------------------------------------------------------------
# BayesianMap detection (Observation output)
# ---------------------------------------------------------------------------

class TestThresholdBayesianDetection:
    def test_returns_list(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert isinstance(td.process(), list)

    def test_detects_one_region(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert len(td.process()) == 1

    def test_emits_observation(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert isinstance(td.process()[0], Observation)

    def test_confidence_near_input_confidence(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert td.process()[0].confidence == pytest.approx(0.9, abs=0.02)

    def test_confidence_in_unit_interval(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        for obs in td.process():
            assert 0.0 <= obs.confidence <= 1.0

    def test_event_has_geometry(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert isinstance(td.process()[0].geometry, BaseGeometry)

    def test_event_geometry_is_polygon(self, pom_with_event):
        from shapely.geometry import MultiPolygon, Polygon
        td = Threshold(0.7)(pom_with_event)
        assert isinstance(td.process()[0].geometry, (Polygon, MultiPolygon))

    def test_event_geometry_has_positive_area(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert td.process()[0].geometry.area > 0

    def test_event_geometry_contains_detected_point(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert td.process()[0].geometry.contains(Point(CENTRE_X, CENTRE_Y))

    def test_event_timestamp_from_predecessor(self, pom_with_event):
        td = Threshold(0.7)(pom_with_event)
        assert td.process()[0].timestamp == pytest.approx(10.0)

    def test_no_detection_below_threshold(self, pom):
        td = Threshold(0.7)(pom)
        assert td.process() == []

    def test_no_detection_when_threshold_above_peak(self, pom_with_event):
        td = Threshold(0.95)(pom_with_event)
        assert td.process() == []


# ---------------------------------------------------------------------------
# Multiple regions
# ---------------------------------------------------------------------------

class TestMultipleRegions:
    def test_two_separated_events_give_two_alarms(self, pom):
        event_a = Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=0.9)
        event_b = Observation(geometry=Point(500015.0, CENTRE_Y), timestamp=2.0, confidence=0.9)
        pom.process(event_a)
        pom.process(event_b)
        td = Threshold(0.7)(pom)
        assert len(td.process()) >= 2


# ---------------------------------------------------------------------------
# Successor push
# ---------------------------------------------------------------------------

class TestSuccessorPush:
    def test_detected_events_pushed_to_successors(self, pom_with_event):
        from mufasa.node import Node

        class _Sink(Node):
            received = []
            _input_types = [Observation]
            _output_type = None
            def process(self, obs): self.received.append(obs)
            def get_config(self): return {}

        td = Threshold(0.7)(pom_with_event)
        sink = _Sink()(td)
        sink.received.clear()
        events = td.process()
        assert len(sink.received) == len(events)

    def test_no_push_when_no_detection(self, pom):
        from mufasa.node import Node

        class _Sink(Node):
            count = 0
            _input_types = [Observation]
            _output_type = None
            def process(self, obs): _Sink.count += 1
            def get_config(self): return {}

        td = Threshold(0.7)(pom)
        _Sink()(td)
        _Sink.count = 0
        td.process()
        assert _Sink.count == 0


# ---------------------------------------------------------------------------
# Accumulation (alarm_timeout_s)
# ---------------------------------------------------------------------------

def _wire_collector(td):
    received = []

    class _Collector:
        _successors = []
        def process(self, obs):
            received.append(obs)

    td._successors.append(_Collector())
    return received


class TestAccumulation:
    def test_first_call_always_fires(self, pom):
        td = Threshold(0.7, alarm_timeout_s=60.0)(pom)
        received = _wire_collector(td)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=0.0, confidence=0.9))
        assert len(received) >= 1

    def test_no_alarm_within_timeout(self, pom):
        td = Threshold(0.7, alarm_timeout_s=60.0)(pom)
        received = _wire_collector(td)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=0.0,  confidence=0.9))
        n = len(received)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=30.0, confidence=0.9))
        assert len(received) == n

    def test_alarm_fires_after_timeout(self, pom):
        td = Threshold(0.7, alarm_timeout_s=60.0)(pom)
        received = _wire_collector(td)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=0.0,  confidence=0.9))
        n = len(received)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=70.0, confidence=0.9))
        assert len(received) > n

    def test_accumulation_retains_max_probability(self, pom):
        td = Threshold(0.5, alarm_timeout_s=60.0)(pom)
        _wire_collector(td)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=0.0,  confidence=0.9))
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=30.0, confidence=0.6))
        assert td._max_grid is not None
        assert td._max_grid.max() > 0.5

    def test_reset_clears_accumulator(self, pom):
        td = Threshold(0.7, alarm_timeout_s=60.0)(pom)
        _wire_collector(td)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=0.0, confidence=0.9))
        td.reset()
        assert td._max_grid is None
        assert td._last_alarm_time is None

    def test_zero_timeout_always_alarms(self, pom):
        td = Threshold(0.7, alarm_timeout_s=0.0)(pom)
        received = _wire_collector(td)
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=0.0,  confidence=0.9))
        n = len(received)
        assert n >= 1
        pom.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.9))
        assert len(received) > n


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_get_config_has_threshold(self):
        assert Threshold(0.6).get_config()["threshold"] == pytest.approx(0.6)

    def test_get_config_has_alarm_timeout_s(self):
        assert Threshold(0.6, alarm_timeout_s=30.0).get_config()["alarm_timeout_s"] == pytest.approx(30.0)

    def test_get_config_is_serializable(self):
        import json
        json.dumps(Threshold(0.75, alarm_timeout_s=60.0, dilation_px=1, simplify_m=5.0).get_config())
