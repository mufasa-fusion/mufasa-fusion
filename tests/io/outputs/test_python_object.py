import numpy as np
import pytest
from rasterio.transform import from_bounds
from rasterio.crs import CRS

from mufasa.io.outputs.base import OutputNode
from mufasa.io.outputs.python_object import LocationOutput, MapOutput
from mufasa.map import BayesianMap, Map


def _make_map(value: float = 1.0) -> BayesianMap:
    transform = from_bounds(0, 0, 10, 10, 2, 2)
    crs = CRS.from_epsg(32633)
    data = np.full((2, 2), value, dtype=np.float64)
    return BayesianMap(data, transform, crs)


class _FakeMapNode:
    """Predecessor stub that exposes .map; set node.map.timestamp to control rate-limiting."""
    def __init__(self, m: Map):
        self._map = m
        self._successors = []

    @property
    def output_type(self):
        return BayesianMap

    @property
    def map(self) -> Map:
        return self._map


class TestLocationOutput:
    def test_is_file_output_mixin(self):
        assert issubclass(LocationOutput, OutputNode)

    def test_result_starts_empty(self):
        assert LocationOutput().result == []

    def test_save_is_noop(self):
        LocationOutput().save()


class TestMapOutput:
    def test_is_file_output_mixin(self):
        assert issubclass(MapOutput, OutputNode)

    def test_result_starts_empty(self):
        assert MapOutput().result == []

    def test_save_is_noop(self):
        MapOutput().save()

    def test_input_types_includes_map(self):
        assert Map in MapOutput().input_types

    def test_output_type_is_none(self):
        assert MapOutput().output_type is None

    def test_default_snapshot_interval(self):
        assert MapOutput().snapshot_interval_s == pytest.approx(5.0)

    def test_custom_snapshot_interval(self):
        assert MapOutput(snapshot_interval_s=10.0).snapshot_interval_s == pytest.approx(10.0)

    def test_negative_interval_raises(self):
        with pytest.raises(ValueError):
            MapOutput(snapshot_interval_s=-1.0)

    def test_zero_interval_stores_every_update(self):
        assert MapOutput(snapshot_interval_s=0.0).snapshot_interval_s == pytest.approx(0.0)

    def test_get_config_has_snapshot_interval(self):
        assert MapOutput(snapshot_interval_s=10.0).get_config() == {"snapshot_interval_s": 10.0}

    # ------------------------------------------------------------------
    # Snapshot storage
    # ------------------------------------------------------------------

    def test_first_update_always_stored(self):
        node = _FakeMapNode(_make_map(1.0))
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [node]
        out.process()
        assert len(out.result) == 1

    def test_stores_copy_not_reference(self):
        m = _make_map(1.0)
        node = _FakeMapNode(m)
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [node]
        out.process()
        m.data[:] = 99.0
        assert out.result[0].data[0, 0] == pytest.approx(1.0)

    def test_result_is_map_instance(self):
        node = _FakeMapNode(_make_map())
        out = MapOutput()
        out._predecessors = [node]
        out.process()
        assert isinstance(out.result[0], Map)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def test_update_within_interval_not_stored(self):
        node = _FakeMapNode(_make_map())
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [node]
        out.process()                    # t=0  → stored (first)
        node.map.timestamp = 3.0
        out.process()                    # t=3  → skipped (3 < 5)
        assert len(out.result) == 1

    def test_update_at_interval_boundary_not_stored(self):
        node = _FakeMapNode(_make_map())
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [node]
        out.process()                    # t=0  → stored
        node.map.timestamp = 4.9
        out.process()                    # t=4.9 < 5 → skipped
        assert len(out.result) == 1

    def test_update_after_interval_stored(self):
        node = _FakeMapNode(_make_map())
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [node]
        out.process()                    # t=0  → stored
        node.map.timestamp = 5.0
        out.process()                    # t=5  → stored (5 >= 5)
        assert len(out.result) == 2

    def test_multiple_intervals_stored_correctly(self):
        node = _FakeMapNode(_make_map())
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [node]
        for t in [0.0, 2.0, 4.0, 5.0, 7.0, 10.0, 12.0]:
            node.map.timestamp = t
            out.process()
        # stored at t=0, t=5, t=10 → 3 snapshots
        assert len(out.result) == 3

    def test_zero_interval_stores_every_call(self):
        node = _FakeMapNode(_make_map())
        out = MapOutput(snapshot_interval_s=0.0)
        out._predecessors = [node]
        for t in [0.0, 0.1, 0.2]:
            node.map.timestamp = t
            out.process()
        assert len(out.result) == 3

    def test_same_timestamp_on_repeat_calls_suppressed(self):
        """Repeated process() calls at the same timestamp respect the interval."""
        node = _FakeMapNode(_make_map())          # timestamp stays 0.0
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [node]
        out.process()   # stored (first)
        out.process()   # skipped (0 - 0 = 0 < 5)
        assert len(out.result) == 1

    # ------------------------------------------------------------------
    # Wiring and pipeline integration
    # ------------------------------------------------------------------

    def test_wires_to_bayesian_fusion(self):
        from mufasa.nodes.fusion import BayesianFusion
        from mufasa.nodes.mapping import POM
        pom = POM(decay_s=100.0)
        fusion = BayesianFusion()(pom)
        out = MapOutput()(fusion)
        assert fusion in out._predecessors

    def test_triggered_via_pipeline(self):
        from shapely.geometry import Point
        from mufasa import BoundingBox, Observation
        from mufasa.nodes.mapping import POM
        from mufasa.nodes.fusion import BayesianFusion

        CRS  = "EPSG:32633"
        BBOX = BoundingBox(500000., 5200000., 500100., 5200100.)
        RES  = (10., 10.)

        pom = POM(decay_s=100.0)
        pom.configure(CRS, BBOX, RES)
        fusion = BayesianFusion()(pom)
        fusion.configure(CRS, BBOX, RES)
        out = MapOutput(snapshot_interval_s=0.0)   # capture every update
        out._predecessors = [fusion]
        fusion._successors.append(out)

        pom.process(Observation(geometry=Point(500055., 5200045.), timestamp=1.0, confidence=0.9))

        assert len(out.result) == 1
        assert isinstance(out.result[0], Map)

    def test_interval_respected_in_live_pipeline(self):
        """With interval=5, only the first of three rapid events is captured."""
        from shapely.geometry import Point
        from mufasa import BoundingBox, Observation
        from mufasa.nodes.mapping import POM
        from mufasa.nodes.fusion import BayesianFusion

        CRS  = "EPSG:32633"
        BBOX = BoundingBox(500000., 5200000., 500100., 5200100.)
        RES  = (10., 10.)

        pom = POM(decay_s=100.0)
        pom.configure(CRS, BBOX, RES)
        fusion = BayesianFusion()(pom)
        fusion.configure(CRS, BBOX, RES)
        out = MapOutput(snapshot_interval_s=5.0)
        out._predecessors = [fusion]
        fusion._successors.append(out)

        for t in [0.0, 1.0, 2.0]:
            pom.process(Observation(geometry=Point(500055., 5200045.),
                              timestamp=t, confidence=0.9))

        assert len(out.result) == 1   # only t=0 captured; t=1 and t=2 within interval
