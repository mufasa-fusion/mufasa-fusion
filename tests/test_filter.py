"""Tests for ObservationFilter."""
import pytest
from shapely.geometry import Point

from mufasa import Observation, Location
from mufasa.nodes.util import ObservationFilter


def _obs(confidence=0.8, timestamp=1.0, **props):
    return Observation(geometry=Point(0, 0), timestamp=timestamp,
                       confidence=confidence, properties=props)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TestObservationFilterTypes:
    def test_accepted_input_is_observation(self):
        assert Observation in ObservationFilter().input_types

    def test_does_not_accept_bare_location(self):
        assert Location not in ObservationFilter().input_types

    def test_output_type_is_observation(self):
        assert ObservationFilter().output_type is Observation


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestObservationFilterInit:
    def test_defaults_pass_everything(self):
        f = ObservationFilter()
        assert f.min_confidence == 0.0
        assert f.start_time is None
        assert f.end_time is None
        assert f._patterns == {}

    def test_min_confidence_stored(self):
        assert ObservationFilter(min_confidence=0.5).min_confidence == 0.5

    def test_time_window_stored(self):
        f = ObservationFilter(start_time=10.0, end_time=20.0)
        assert f.start_time == 10.0
        assert f.end_time == 20.0

    def test_property_patterns_compiled(self):
        f = ObservationFilter(properties={"source": "radar.*"})
        assert "source" in f._patterns

    def test_invalid_min_confidence_raises(self):
        with pytest.raises(ValueError):
            ObservationFilter(min_confidence=1.5)

    def test_negative_min_confidence_raises(self):
        with pytest.raises(ValueError):
            ObservationFilter(min_confidence=-0.1)


# ---------------------------------------------------------------------------
# Filtering logic — confidence
# ---------------------------------------------------------------------------

class TestConfidenceFilter:
    def test_passes_by_default(self):
        assert ObservationFilter()._passes(_obs())

    def test_blocks_low_confidence(self):
        assert not ObservationFilter(min_confidence=0.9)._passes(_obs(confidence=0.5))

    def test_passes_exact_confidence(self):
        assert ObservationFilter(min_confidence=0.5)._passes(_obs(confidence=0.5))


# ---------------------------------------------------------------------------
# Filtering logic — time window
# ---------------------------------------------------------------------------

class TestTimeWindowFilter:
    def test_passes_within_window(self):
        f = ObservationFilter(start_time=10.0, end_time=20.0)
        assert f._passes(_obs(timestamp=15.0))

    def test_passes_at_start_boundary(self):
        f = ObservationFilter(start_time=10.0)
        assert f._passes(_obs(timestamp=10.0))

    def test_blocks_before_start(self):
        f = ObservationFilter(start_time=10.0)
        assert not f._passes(_obs(timestamp=9.9))

    def test_blocks_at_end_boundary(self):
        f = ObservationFilter(end_time=20.0)
        assert not f._passes(_obs(timestamp=20.0))

    def test_passes_just_before_end(self):
        f = ObservationFilter(end_time=20.0)
        assert f._passes(_obs(timestamp=19.9))

    def test_blocks_observation_before_start_time(self):
        f = ObservationFilter(start_time=10.0)
        obs = Observation(geometry=Point(0, 0), timestamp=0.0, confidence=0.8)
        assert not f._passes(obs)

    def test_start_only_passes_after(self):
        f = ObservationFilter(start_time=5.0)
        assert f._passes(_obs(timestamp=100.0))


# ---------------------------------------------------------------------------
# Filtering logic — properties
# ---------------------------------------------------------------------------

class TestPropertyFilter:
    def test_passes_matching_property(self):
        f = ObservationFilter(properties={"source": "radar"})
        assert f._passes(_obs(source="radar"))

    def test_blocks_non_matching_property(self):
        f = ObservationFilter(properties={"source": "radar"})
        assert not f._passes(_obs(source="lidar"))

    def test_passes_regex_pattern(self):
        f = ObservationFilter(properties={"source": "radar.*"})
        assert f._passes(_obs(source="radar_01"))

    def test_blocks_partial_regex_match(self):
        f = ObservationFilter(properties={"source": "radar"})
        assert not f._passes(_obs(source="radar_01"))

    def test_missing_property_key_blocks(self):
        f = ObservationFilter(properties={"source": "radar"})
        assert not f._passes(_obs())

    def test_multiple_properties_all_must_match(self):
        f = ObservationFilter(properties={"source": "radar", "type": "track"})
        assert f._passes(_obs(source="radar", type="track"))
        assert not f._passes(_obs(source="radar", type="detection"))


# ---------------------------------------------------------------------------
# Combined criteria
# ---------------------------------------------------------------------------

class TestCombinedFilter:
    def test_confidence_and_property_both_required(self):
        f = ObservationFilter(min_confidence=0.7, properties={"source": "radar"})
        assert f._passes(_obs(confidence=0.9, source="radar"))
        assert not f._passes(_obs(confidence=0.5, source="radar"))
        assert not f._passes(_obs(confidence=0.9, source="lidar"))

    def test_confidence_time_and_property_all_required(self):
        f = ObservationFilter(min_confidence=0.5, start_time=10.0, end_time=20.0,
                              properties={"source": "radar"})
        assert f._passes(_obs(confidence=0.8, timestamp=15.0, source="radar"))
        assert not f._passes(_obs(confidence=0.8, timestamp=5.0, source="radar"))
        assert not f._passes(_obs(confidence=0.8, timestamp=15.0, source="lidar"))
        assert not f._passes(_obs(confidence=0.3, timestamp=15.0, source="radar"))


# ---------------------------------------------------------------------------
# Successor push
# ---------------------------------------------------------------------------

class TestObservationFilterPush:
    def _make_chain(self, **filter_kwargs):
        from mufasa.node import Node

        class _Source(Node):
            _input_types = []
            _output_type = Observation
            def process(self): pass
            def get_config(self): return {}

        class _Sink(Node):
            received = []
            _input_types = [Observation]
            _output_type = None
            def process(self, obs): self.received.append(obs)
            def get_config(self): return {}

        src  = _Source()
        filt = ObservationFilter(**filter_kwargs)(src)
        sink = _Sink()(filt)
        sink.received = []
        return filt, sink

    def test_passing_observation_forwarded(self):
        filt, sink = self._make_chain(min_confidence=0.5)
        filt.process(_obs(confidence=0.9))
        assert len(sink.received) == 1

    def test_blocked_observation_not_forwarded(self):
        filt, sink = self._make_chain(min_confidence=0.9)
        filt.process(_obs(confidence=0.5))
        assert len(sink.received) == 0

    def test_time_window_blocks_outside(self):
        filt, sink = self._make_chain(start_time=10.0, end_time=20.0)
        filt.process(_obs(timestamp=5.0))
        filt.process(_obs(timestamp=15.0))
        filt.process(_obs(timestamp=25.0))
        assert len(sink.received) == 1

    def test_multiple_observations_filtered_correctly(self):
        filt, sink = self._make_chain(min_confidence=0.6)
        filt.process(_obs(confidence=0.8))
        filt.process(_obs(confidence=0.3))
        filt.process(_obs(confidence=0.7))
        assert len(sink.received) == 2


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestObservationFilterConfig:
    def test_config_has_min_confidence(self):
        assert ObservationFilter(min_confidence=0.5).get_config()["min_confidence"] == 0.5

    def test_config_has_time_window(self):
        cfg = ObservationFilter(start_time=10.0, end_time=20.0).get_config()
        assert cfg["start_time"] == 10.0
        assert cfg["end_time"] == 20.0

    def test_config_has_properties(self):
        cfg = ObservationFilter(properties={"source": "radar.*"}).get_config()
        assert cfg["properties"] == {"source": "radar.*"}

    def test_config_serializable(self):
        import json
        cfg = ObservationFilter(min_confidence=0.5, start_time=0.0,
                                properties={"source": "radar"}).get_config()
        json.dumps(cfg)
