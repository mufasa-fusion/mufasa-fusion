"""Tests for MapFusion base and all concrete fusion nodes."""
import numpy as np
import pytest

from mufasa import BayesianMap, Map, Node
from mufasa.nodes.fusion import BayesianFusion, LogicalAnd, LogicalOr, MapFusion

from .conftest import CENTRE_X, CENTRE_Y
from tests.helpers import CRS, BBOX, RES


# ---------------------------------------------------------------------------
# BayesianFusion
# ---------------------------------------------------------------------------

class TestBayesianFusionTypes:
    def test_is_map_fusion_subclass(self):
        assert issubclass(BayesianFusion, MapFusion)

    def test_accepted_input_type_is_bayesian_map(self):
        assert BayesianMap in BayesianFusion().input_types

    def test_does_not_accept_plain_map(self):
        assert Map not in BayesianFusion().input_types

    def test_output_type_is_bayesian_map(self):
        assert BayesianFusion().output_type is BayesianMap

    def test_wires_to_pom(self, pom_a):
        bf = BayesianFusion()(pom_a)
        assert pom_a in bf._predecessors


class TestBayesianFusionProcess:
    def test_map_before_process_raises(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        with pytest.raises(RuntimeError):
            _ = bf.map

    def test_process_returns_bayesian_map(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        assert isinstance(bf.process(), BayesianMap)

    def test_map_property_returns_bayesian_map(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        assert isinstance(bf.map, BayesianMap)

    def test_map_is_same_object_across_calls(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        m1 = bf.map
        bf.process()
        assert bf.map is m1

    def test_output_probabilities_in_unit_interval(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        probs = bf.map.probabilities
        assert np.all(probs >= 0.0) and np.all(probs <= 1.0)

    def test_fused_log_odds_equals_sum_of_inputs(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        assert bf.map.data[5, 5] == pytest.approx(
            pom_a.map.data[5, 5] + pom_b.map.data[5, 5], rel=1e-5
        )

    def test_fused_probability_higher_than_either_input(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        assert bf.map.probabilities[5, 5] > pom_a.map.probabilities[5, 5]
        assert bf.map.probabilities[5, 5] > pom_b.map.probabilities[5, 5]

    def test_output_transform_matches_predecessor(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        assert bf.map.transform == pom_a.map.transform

    def test_output_crs_matches_predecessor(self, pom_a, pom_b):
        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        assert bf.map.crs == pom_a.map.crs

    def test_single_predecessor_passes_through(self, pom_a):
        bf = BayesianFusion()(pom_a)
        bf.configure(CRS, BBOX, RES)
        bf.process()
        assert bf.map.data == pytest.approx(pom_a.map.data, rel=1e-5)

    def test_process_triggers_successors(self, pom_a, pom_b):
        call_count = []

        class Sink(Node):
            _input_types = [BayesianMap]
            _output_type = None
            def process(self): call_count.append(1)
            def get_config(self): return {}

        bf = BayesianFusion()(pom_a, pom_b)
        bf.configure(CRS, BBOX, RES)
        Sink()(bf)
        bf.process()
        assert call_count == [1]

    def test_chained_fusion(self, pom_a, pom_b, pom_low):
        bf1 = BayesianFusion()(pom_a, pom_b)
        bf2 = BayesianFusion()(bf1, pom_low)
        bf1.configure(CRS, BBOX, RES)
        bf2.configure(CRS, BBOX, RES)
        bf1.process()
        bf2.process()
        assert isinstance(bf2.map, BayesianMap)

    def test_get_config(self):
        assert BayesianFusion().get_config() == {}


# ---------------------------------------------------------------------------
# LogicalAnd
# ---------------------------------------------------------------------------

class TestLogicalAndTypes:
    def test_is_map_fusion_subclass(self):
        assert issubclass(LogicalAnd, MapFusion)

    def test_accepted_input_is_bayesian_map(self):
        assert BayesianMap in LogicalAnd().input_types

    def test_does_not_accept_plain_map(self):
        assert Map not in LogicalAnd().input_types

    def test_output_type_is_bayesian_map(self):
        assert LogicalAnd().output_type is BayesianMap


class TestLogicalAndProcess:
    def test_returns_bayesian_map(self, pom_a, pom_b):
        la = LogicalAnd()(pom_a, pom_b)
        la.configure(CRS, BBOX, RES)
        assert isinstance(la.process(), BayesianMap)

    def test_map_is_same_object_across_calls(self, pom_a, pom_b):
        la = LogicalAnd()(pom_a, pom_b)
        la.configure(CRS, BBOX, RES)
        la.process()
        m1 = la.map
        la.process()
        assert la.map is m1

    def test_result_equals_min_log_odds(self, pom_a, pom_b):
        la = LogicalAnd()(pom_a, pom_b)
        la.configure(CRS, BBOX, RES)
        la.process()
        assert la.map.data[5, 5] == pytest.approx(
            min(pom_a.map.data[5, 5], pom_b.map.data[5, 5]), rel=1e-5
        )

    def test_low_confidence_dominates(self, pom_a, pom_low):
        la = LogicalAnd()(pom_a, pom_low)
        la.configure(CRS, BBOX, RES)
        la.process()
        assert la.map.data[5, 5] < pom_a.map.data[5, 5]

    def test_output_probabilities_in_unit_interval(self, pom_a, pom_b):
        la = LogicalAnd()(pom_a, pom_b)
        la.configure(CRS, BBOX, RES)
        la.process()
        probs = la.map.probabilities
        assert np.all(probs >= 0.0) and np.all(probs <= 1.0)

    def test_get_config(self):
        assert LogicalAnd().get_config() == {}


# ---------------------------------------------------------------------------
# LogicalOr
# ---------------------------------------------------------------------------

class TestLogicalOrTypes:
    def test_is_map_fusion_subclass(self):
        assert issubclass(LogicalOr, MapFusion)

    def test_accepted_input_is_bayesian_map(self):
        assert BayesianMap in LogicalOr().input_types

    def test_output_type_is_bayesian_map(self):
        assert LogicalOr().output_type is BayesianMap


class TestLogicalOrProcess:
    def test_returns_bayesian_map(self, pom_a, pom_b):
        lo = LogicalOr()(pom_a, pom_b)
        lo.configure(CRS, BBOX, RES)
        assert isinstance(lo.process(), BayesianMap)

    def test_map_is_same_object_across_calls(self, pom_a, pom_b):
        lo = LogicalOr()(pom_a, pom_b)
        lo.configure(CRS, BBOX, RES)
        lo.process()
        m1 = lo.map
        lo.process()
        assert lo.map is m1

    def test_result_equals_max_log_odds(self, pom_a, pom_b):
        lo_node = LogicalOr()(pom_a, pom_b)
        lo_node.configure(CRS, BBOX, RES)
        lo_node.process()
        assert lo_node.map.data[5, 5] == pytest.approx(
            max(pom_a.map.data[5, 5], pom_b.map.data[5, 5]), rel=1e-5
        )

    def test_high_confidence_dominates(self, pom_a, pom_low):
        lo_node = LogicalOr()(pom_a, pom_low)
        lo_node.configure(CRS, BBOX, RES)
        lo_node.process()
        assert lo_node.map.data[5, 5] > pom_low.map.data[5, 5]

    def test_output_probabilities_in_unit_interval(self, pom_a, pom_b):
        lo_node = LogicalOr()(pom_a, pom_b)
        lo_node.configure(CRS, BBOX, RES)
        lo_node.process()
        probs = lo_node.map.probabilities
        assert np.all(probs >= 0.0) and np.all(probs <= 1.0)

    def test_get_config(self):
        assert LogicalOr().get_config() == {}


# ---------------------------------------------------------------------------
# AND / OR relationship
# ---------------------------------------------------------------------------

class TestLogicalAndOrRelationship:
    def test_and_le_or_at_every_cell(self, pom_a, pom_b):
        la = LogicalAnd()(pom_a, pom_b); la.configure(CRS, BBOX, RES)
        lo = LogicalOr()(pom_a, pom_b);  lo.configure(CRS, BBOX, RES)
        la.process()
        lo.process()
        assert np.all(la.map.data <= lo.map.data + 1e-9)

    def test_and_or_equal_when_single_predecessor(self, pom_a):
        la = LogicalAnd()(pom_a); la.configure(CRS, BBOX, RES)
        lo = LogicalOr()(pom_a);  lo.configure(CRS, BBOX, RES)
        la.process()
        lo.process()
        assert la.map.data == pytest.approx(lo.map.data, rel=1e-5)


class TestMapFusionTimestamp:
    """map.timestamp must propagate through fusion so Threshold can timestamp alarms."""

    def test_map_timestamp_matches_predecessor(self, pom_a):
        # pom_a processed an Observation at timestamp=10.0
        fusion = BayesianFusion()(pom_a)
        fusion.configure(CRS, BBOX, RES)
        fusion.process()
        assert fusion.map.timestamp == pytest.approx(10.0)

    def test_map_timestamp_is_max_of_predecessors(self, pom_a, pom_b):
        # Both poms have timestamp=10.0 from conftest; verify max is returned
        fusion = BayesianFusion()(pom_a, pom_b)
        fusion.configure(CRS, BBOX, RES)
        fusion.process()
        assert fusion.map.timestamp == pytest.approx(10.0)

    def test_map_timestamp_takes_later_of_two_predecessors(self):
        from shapely.geometry import Point
        from mufasa import BoundingBox, Observation
        from mufasa.nodes.mapping import POM
        CRS  = "EPSG:32633"
        BBOX = BoundingBox(500000., 5200000., 500100., 5200100.)
        RES  = (10., 10.)
        p1 = POM(decay_s=100.0); p1.configure(CRS, BBOX, RES)
        p2 = POM(decay_s=100.0); p2.configure(CRS, BBOX, RES)
        p1.process(Observation(geometry=Point(500055., 5200045.), timestamp=5.0,  confidence=0.8))
        p2.process(Observation(geometry=Point(500055., 5200045.), timestamp=20.0, confidence=0.8))
        fusion = BayesianFusion()(p1, p2)
        fusion.configure(CRS, BBOX, RES)
        fusion.process()
        assert fusion.map.timestamp == pytest.approx(20.0)

    def test_map_timestamp_zero_before_any_event(self):
        from mufasa import BoundingBox
        from mufasa.nodes.mapping import POM
        p = POM(decay_s=100.0)
        p.configure("EPSG:32633", BoundingBox(500000., 5200000., 500100., 5200100.), (10., 10.))
        fusion = BayesianFusion()(p)
        fusion.configure("EPSG:32633", BoundingBox(500000., 5200000., 500100., 5200100.), (10., 10.))
        fusion.process()
        assert fusion.map.timestamp == pytest.approx(0.0)

    def test_threshold_decision_alarm_has_timestamp_from_fusion(self):
        """End-to-end: alarm Observation timestamp must not be None when fusion is predecessor."""
        from shapely.geometry import Point
        from mufasa import BoundingBox, Observation
        from mufasa.nodes.mapping import POM
        from mufasa.nodes.detection import Threshold
        CRS  = "EPSG:32633"
        BBOX = BoundingBox(500000., 5200000., 500100., 5200100.)
        RES  = (10., 10.)
        pom = POM(decay_s=100.0); pom.configure(CRS, BBOX, RES)
        fusion = BayesianFusion()(pom); fusion.configure(CRS, BBOX, RES)
        td = Threshold(0.7)(fusion)
        alarms = []
        class _Sink:
            _successors = []
            def process(self, ev): alarms.append(ev)
        td._successors.append(_Sink())
        pom.process(Observation(geometry=Point(500055., 5200045.), timestamp=42.0, confidence=0.9))
        assert alarms, "expected at least one alarm"
        assert alarms[0].timestamp == pytest.approx(42.0)
