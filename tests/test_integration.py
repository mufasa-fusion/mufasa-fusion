"""End-to-end pipeline integration tests.

Ports the core scenarios from tests_old/test_bayesian.py and tests_old/test_and.py.
Nodes are wired and configured directly (no Graph) so tests stay focused on the
processing logic rather than the DAG machinery.

Math reference (EPSG:32633, 100×100 m grid, 10 m/px, prior=0.5):
    logit(0.9)         ≈  2.197  logit(0.1) ≈ -2.197  logit(0.8) ≈ 1.386
    expit(2.197)       ≈  0.9
    expit(4.394)       ≈  0.988   (two POMs at 0.9)
    expit(3.583)       ≈  0.972   (POM 0.9 + Static 0.8)
    expit(0.0)         =  0.5     (POM 0.9 + Static 0.1 cancel out)
"""
import numpy as np
import pytest
from shapely.geometry import Point, box as shapely_box

from mufasa import BoundingBox, Observation
from mufasa.nodes.mapping import POM, StaticMap
from mufasa.nodes.fusion import BayesianFusion, LogicalAnd
from mufasa.nodes.detection import Threshold
from tests.helpers import write_geojson as _write_geojson

# ---------------------------------------------------------------------------
# Shared spatial constants — same 100 m × 100 m, 10 × 10 grid used in
# sensor tests so CENTRE_X/CENTRE_Y map to pixel (row=5, col=5).
# ---------------------------------------------------------------------------

CRS      = "EPSG:32633"
BBOX     = BoundingBox(500000.0, 5200000.0, 500100.0, 5200100.0)
RES      = (10.0, 10.0)
CENTRE_X = 500055.0
CENTRE_Y = 5200045.0

_FULL_POLY = shapely_box(500000.0, 5200000.0, 500100.0, 5200100.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pom(decay_s: float = 300.0) -> POM:
    pom = POM(decay_s=decay_s, prior=0.5)
    pom.configure(CRS, BBOX, RES)
    return pom


def _wire_alarm_collector(td: Threshold) -> list:
    """Attach a list-collecting sink as successor of td; return the list."""
    received: list[Observation] = []

    class _Sink:
        _successors: list = []

        def process(self, obs: Observation) -> None:
            received.append(obs)

    td._successors.append(_Sink())
    return received


def _centre_event(timestamp: float = 1.0, confidence: float = 0.9) -> Observation:
    return Observation(
        geometry=Point(CENTRE_X, CENTRE_Y),
        timestamp=timestamp,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# BayesianFusion pipeline
# ---------------------------------------------------------------------------

class TestBayesianFusionPipeline:

    def test_single_pom_fires_alarm(self):
        """POM at confidence=0.9 → prob≈0.9 > threshold=0.7 → alarm fires."""
        pom    = _make_pom()
        fusion = BayesianFusion()(pom)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom.process(_centre_event())

        assert len(rcv) >= 1
        assert all(isinstance(e, Observation) for e in rcv)

    def test_two_poms_bayesian_fusion_fires_alarm(self):
        """Two POMs, both at 0.9 confidence, fuse to ~0.988 > threshold=0.7."""
        pom_a = _make_pom()
        pom_b = _make_pom()
        fusion = BayesianFusion()(pom_a, pom_b)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event(timestamp=1.0))
        pom_b.process(_centre_event(timestamp=2.0))

        assert len(rcv) >= 1

    def test_two_poms_high_threshold_no_alarm(self):
        """Two POMs at 0.9 fuse to ~0.988; threshold=0.99 → no alarm ever fires."""
        pom_a = _make_pom()
        pom_b = _make_pom()
        fusion = BayesianFusion()(pom_a, pom_b)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.99)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event(timestamp=1.0))
        pom_b.process(_centre_event(timestamp=2.0))

        assert len(rcv) == 0

    def test_fused_alarm_has_geometry(self):
        pom    = _make_pom()
        fusion = BayesianFusion()(pom)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom.process(_centre_event())

        assert rcv
        assert rcv[0].geometry is not None

    def test_fused_alarm_confidence_in_unit_interval(self):
        pom    = _make_pom()
        fusion = BayesianFusion()(pom)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom.process(_centre_event())

        for alarm in rcv:
            assert 0.0 <= alarm.confidence <= 1.0

    def test_alarm_confidence_approximately_input_confidence(self):
        """Alarm confidence should be close to the Observation confidence for a clean hit."""
        pom    = _make_pom()
        fusion = BayesianFusion()(pom)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom.process(_centre_event(confidence=0.9))

        assert rcv
        assert abs(rcv[-1].confidence - 0.9) < 0.05


# ---------------------------------------------------------------------------
# StaticMap with BayesianFusion
# ---------------------------------------------------------------------------

class TestBayesianFusionWithStaticMap:

    def test_high_prior_static_boosts_below_threshold_alarm(self, tmp_path):
        """Single POM at 0.9 → prob≈0.9 < threshold=0.95 alone (no alarm).
        Adding StaticMap(prior=0.8): fusion ≈ expit(2.197+1.386)=0.972 > 0.95 → alarm fires."""
        # Confirm baseline: single POM does NOT reach 0.95
        pom_baseline = _make_pom()
        fusion_base  = BayesianFusion()(pom_baseline)
        fusion_base.configure(CRS, BBOX, RES)
        td_base      = Threshold(0.95)(fusion_base)
        rcv_base     = _wire_alarm_collector(td_base)
        pom_baseline.process(_centre_event())
        assert len(rcv_base) == 0, "baseline: single POM should not reach threshold=0.95"

        # Now with the static booster
        path = tmp_path / "static_high.geojson"
        _write_geojson(path, [_FULL_POLY], confidences=[0.8])

        pom    = _make_pom()
        static = StaticMap(source=str(path))
        static.configure(CRS, BBOX, RES)
        fusion = BayesianFusion()(pom, static)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.95)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom.process(_centre_event())

        assert len(rcv) >= 1

    def test_low_prior_static_suppresses_alarm(self, tmp_path):
        """Single POM at 0.9 → threshold=0.7 fires alone.
        Adding StaticMap(prior=0.1): fusion = expit(2.197-2.197)=0.5 < 0.7 → no alarm."""
        # Confirm baseline: single POM fires
        pom_baseline = _make_pom()
        td_base      = Threshold(0.7)(pom_baseline)
        rcv_base     = _wire_alarm_collector(td_base)
        pom_baseline.process(_centre_event())
        assert len(rcv_base) >= 1, "baseline: single POM should fire threshold=0.7"

        # Now with the suppressing static
        path = tmp_path / "static_low.geojson"
        _write_geojson(path, [_FULL_POLY], confidences=[0.1])

        pom    = _make_pom()
        static = StaticMap(source=str(path))
        static.configure(CRS, BBOX, RES)
        fusion = BayesianFusion()(pom, static)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom.process(_centre_event())

        assert len(rcv) == 0

    def test_two_poms_with_static_boost_fire_alarm(self, tmp_path):
        """Two POMs + high-prior StaticMap: confirms additive log-odds stacking."""
        path = tmp_path / "static_boost.geojson"
        _write_geojson(path, [_FULL_POLY], confidences=[0.7])

        pom_a  = _make_pom()
        pom_b  = _make_pom()
        static = StaticMap(source=str(path))
        static.configure(CRS, BBOX, RES)
        fusion = BayesianFusion()(pom_a, pom_b, static)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event(timestamp=1.0))

        assert len(rcv) >= 1


# ---------------------------------------------------------------------------
# LogicalAnd pipeline
# ---------------------------------------------------------------------------

class TestLogicalAndPipeline:

    def test_two_agreeing_poms_fire_alarm(self):
        """Both POMs at 0.9: min log-odds = 2.197, prob≈0.9 > threshold=0.7."""
        pom_a  = _make_pom()
        pom_b  = _make_pom()
        fusion = LogicalAnd()(pom_a, pom_b)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event(timestamp=1.0))
        pom_b.process(_centre_event(timestamp=2.0))

        assert len(rcv) >= 1

    def test_two_agreeing_poms_high_threshold_no_alarm(self):
        """Both POMs at 0.9: min log-odds ≈ 2.197, prob≈0.9 < threshold=0.95 → no alarm."""
        pom_a  = _make_pom()
        pom_b  = _make_pom()
        fusion = LogicalAnd()(pom_a, pom_b)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.95)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event(timestamp=1.0))
        pom_b.process(_centre_event(timestamp=2.0))

        assert len(rcv) == 0

    def test_one_pom_disagreeing_suppresses_alarm(self):
        """AND semantics: if pom_b is at prior (all zeros), min log-odds = 0 → prob=0.5 → no alarm."""
        pom_a  = _make_pom()
        pom_b  = _make_pom()      # pom_b never receives events → data = 0 (prior)
        fusion = LogicalAnd()(pom_a, pom_b)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event())  # only pom_a fires; triggers fusion

        assert len(rcv) == 0

    def test_logical_and_with_static_boost(self, tmp_path):
        """LogicalAnd + static booster: min(pom_log_odds, static_log_odds) at the
        agreement pixel should push fused probability above threshold."""
        path = tmp_path / "static_and.geojson"
        _write_geojson(path, [_FULL_POLY], confidences=[0.8])

        pom_a  = _make_pom()
        pom_b  = _make_pom()
        static = StaticMap(source=str(path))
        static.configure(CRS, BBOX, RES)
        fusion = LogicalAnd()(pom_a, pom_b, static)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event(timestamp=1.0))
        pom_b.process(_centre_event(timestamp=2.0))

        assert len(rcv) >= 1

    def test_logical_and_static_low_prior_suppresses(self, tmp_path):
        """StaticMap at 0.1 is below threshold even when both POMs agree."""
        path = tmp_path / "static_and_low.geojson"
        _write_geojson(path, [_FULL_POLY], confidences=[0.1])

        pom_a  = _make_pom()
        pom_b  = _make_pom()
        static = StaticMap(source=str(path))
        static.configure(CRS, BBOX, RES)
        fusion = LogicalAnd()(pom_a, pom_b, static)
        fusion.configure(CRS, BBOX, RES)
        td     = Threshold(0.7)(fusion)
        rcv    = _wire_alarm_collector(td)

        pom_a.process(_centre_event(timestamp=1.0))
        pom_b.process(_centre_event(timestamp=2.0))

        assert len(rcv) == 0
