"""Tests for StaticMap."""
import numpy as np
import pytest
from scipy.special import logit
from shapely.geometry import box

from mufasa import BayesianMap, BoundingBox
from mufasa.nodes.fusion import BayesianFusion
from mufasa.nodes.mapping import POM, StaticMap

from .conftest import BBOX, CRS, RES
from tests.helpers import write_geojson as _write_geojson

_PMIN = 1e-5
_PMAX = 1.0 - 1e-5

# The full 100 m × 100 m test area in UTM33N
_FULL_BOX  = box(500000.0, 5200000.0, 500100.0, 5200100.0)
# Left half only (x 500000–500050)
_LEFT_BOX  = box(500000.0, 5200000.0, 500050.0, 5200100.0)


# ---------------------------------------------------------------------------
# Type contract
# ---------------------------------------------------------------------------

class TestStaticMapTypes:
    def test_output_type(self):
        s = StaticMap(source="dummy.geojson")
        assert s.output_type is BayesianMap

    def test_input_types_empty(self):
        s = StaticMap(source="dummy.geojson")
        assert s.input_types == frozenset()

    def test_map_raises_before_configure(self):
        s = StaticMap(source="dummy.geojson")
        with pytest.raises(RuntimeError):
            _ = s.map

    def test_invalid_default_prior(self):
        with pytest.raises(ValueError):
            StaticMap(source="x.geojson", default_prior=0.0)
        with pytest.raises(ValueError):
            StaticMap(source="x.geojson", default_prior=1.0)


# ---------------------------------------------------------------------------
# Map population
# ---------------------------------------------------------------------------

class TestStaticMapConfigure:
    def test_covered_pixels_have_correct_log_odds(self, tmp_path):
        path = tmp_path / "static.geojson"
        conf = 0.8
        _write_geojson(path, [_FULL_BOX], confidences=[conf])
        s = StaticMap(source=str(path))
        s.configure(CRS, BBOX, RES)
        data = s.map.data
        # All 100 pixels must be set (none should be NaN)
        assert not np.any(np.isnan(data)), "expected all pixels to be covered"
        expected_lo = logit(np.clip(conf, _PMIN, _PMAX))
        assert np.allclose(data, expected_lo, atol=1e-6)

    def test_uncovered_pixels_are_nan(self, tmp_path):
        path = tmp_path / "static.geojson"
        _write_geojson(path, [_LEFT_BOX], confidences=[0.8])
        s = StaticMap(source=str(path))
        s.configure(CRS, BBOX, RES)
        data = s.map.data
        # Left half must be set, right half must remain NaN
        assert not np.any(np.isnan(data[:, :5])), "left half should be covered"
        assert np.all(np.isnan(data[:, 5:])), "right half should be NaN"

    def test_default_prior_used_when_no_confidence_property(self, tmp_path):
        path = tmp_path / "static.geojson"
        default = 0.3
        _write_geojson(path, [_FULL_BOX])  # no confidence column
        s = StaticMap(source=str(path), default_prior=default)
        s.configure(CRS, BBOX, RES)
        data = s.map.data
        assert not np.any(np.isnan(data))
        expected_lo = logit(np.clip(default, _PMIN, _PMAX))
        assert np.allclose(data, expected_lo, atol=1e-6)

    def test_overlapping_features_take_minimum(self, tmp_path):
        """Where two features overlap the pixel should carry the lower confidence."""
        path = tmp_path / "static.geojson"
        high_conf = 0.9
        low_conf  = 0.3
        _write_geojson(
            path,
            [_FULL_BOX, _LEFT_BOX],
            confidences=[high_conf, low_conf],
        )
        s = StaticMap(source=str(path))
        s.configure(CRS, BBOX, RES)
        data = s.map.data

        lo_low  = logit(np.clip(low_conf,  _PMIN, _PMAX))
        lo_high = logit(np.clip(high_conf, _PMIN, _PMAX))
        # Left half overlapped — should be the lower log-odds
        assert np.allclose(data[:, :5], lo_low,  atol=1e-6)
        # Right half covered only by FULL_BOX — should be the higher log-odds
        assert np.allclose(data[:, 5:], lo_high, atol=1e-6)

    def test_configure_is_idempotent(self, tmp_path):
        """Calling configure() twice replaces the map cleanly."""
        path = tmp_path / "static.geojson"
        _write_geojson(path, [_FULL_BOX], confidences=[0.7])
        s = StaticMap(source=str(path))
        s.configure(CRS, BBOX, RES)
        first = s.map
        s.configure(CRS, BBOX, RES)
        assert s.map is not first


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

class TestStaticMapWiring:
    def test_wires_as_predecessor_to_bayesian_fusion(self, tmp_path):
        path = tmp_path / "static.geojson"
        _write_geojson(path, [_FULL_BOX], confidences=[0.6])
        static = StaticMap(source=str(path))
        pom    = POM(decay_s=100.0)
        fusion = BayesianFusion()(pom, static)
        assert static in fusion._predecessors

    def test_process_is_noop(self, tmp_path):
        path = tmp_path / "static.geojson"
        _write_geojson(path, [_FULL_BOX], confidences=[0.6])
        s = StaticMap(source=str(path))
        s.configure(CRS, BBOX, RES)
        assert s.process() is None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestStaticMapConfig:
    def test_get_config(self):
        s = StaticMap(source="priors.geojson", default_prior=0.3)
        cfg = s.get_config()
        assert cfg == {"source": "priors.geojson", "default_prior": 0.3}
