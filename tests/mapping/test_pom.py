"""Tests for POM (Probability Occupancy Map)."""
import numpy as np
import pytest
from scipy.special import expit, logit
from shapely.geometry import Point

from mufasa import BayesianMap, BoundingBox, Observation, Map
from mufasa.nodes.mapping import POM

from .conftest import BBOX, CRS, RES, CENTRE_X, CENTRE_Y

_PMIN = 1e-5
_PMAX = 1.0 - 1e-5


@pytest.fixture
def pom():
    p = POM(decay_s=100.0)
    p.configure(CRS, BBOX, RES)
    return p


@pytest.fixture
def center_event():
    return Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.9)


# ---------------------------------------------------------------------------

class TestPOMInit:
    def test_decay_s_stored(self):
        assert POM(decay_s=60.0).decay_s == 60.0

    def test_default_prior(self):
        assert POM(decay_s=100.0).prior == 0.5

    def test_custom_prior_stored(self):
        assert POM(decay_s=100.0, prior=0.7).prior == 0.7

    def test_prior_zero_raises(self):
        with pytest.raises(ValueError):
            POM(decay_s=100.0, prior=0.0)

    def test_prior_one_raises(self):
        with pytest.raises(ValueError):
            POM(decay_s=100.0, prior=1.0)

    def test_prior_negative_raises(self):
        with pytest.raises(ValueError):
            POM(decay_s=100.0, prior=-0.1)


class TestPOMTypes:
    def test_output_type_is_bayesian_map(self):
        assert POM(100.0).output_type is BayesianMap

    def test_bayesian_map_is_subclass_of_map(self):
        assert issubclass(BayesianMap, Map)

    def test_map_property_returns_bayesian_map(self, pom):
        assert isinstance(pom.map, BayesianMap)


class TestPOMConfigure:
    def test_data_shape(self, pom):
        assert pom._data.shape == (10, 10)

    def test_default_prior_initialises_data_to_zero_log_odds(self, pom):
        # prior=0.5 → logit(0.5) = 0.0
        assert np.allclose(pom._data, 0.0)

    def test_data_always_initialised_to_zero_log_odds_regardless_of_prior(self):
        # prior is the sensor baseline, not an occupancy prior — map starts neutral (0.5)
        p = POM(decay_s=100.0, prior=0.8)
        p.configure(CRS, BBOX, RES)
        assert np.allclose(p._data, 0.0)


class TestPOMMap:
    def test_map_data_is_log_odds(self, pom, center_event):
        # prior=0.5 → log-odds=0 before Observation; positive after high-confidence Observation
        assert np.allclose(pom.map.data, 0.0)
        pom.process(center_event)
        assert pom.map.data[5, 5] > 0.0

    def test_map_at_prior_before_any_event(self, pom):
        # prior=0.5 → logit(0.5) = 0.0
        assert np.allclose(pom.map.data, 0.0)

    def test_map_log_odds_increase_at_event_location(self, pom, center_event):
        before = pom.map.data[5, 5]
        pom.process(center_event)
        assert pom.map.data[5, 5] > before

    def test_map_confidence_reflected_in_log_odds(self, pom, center_event):
        # confidence=0.9, prior=0.5 → update = logit(0.9) - logit(0.5) ≈ 2.197
        pom.process(center_event)
        assert pom.map.data[5, 5] == pytest.approx(logit(0.9), abs=0.01)

    def test_probabilities_in_unit_interval(self, pom, center_event):
        pom.process(center_event)
        probs = pom.map.probabilities
        assert np.all(probs >= 0.0) and np.all(probs <= 1.0)

    def test_probabilities_confidence_reflected(self, pom, center_event):
        pom.process(center_event)
        assert pom.map.probabilities[5, 5] == pytest.approx(0.9, abs=0.01)

    def test_copy_preserves_bayesian_map_type(self, pom, center_event):
        pom.process(center_event)
        c = pom.map.copy()
        assert isinstance(c, BayesianMap)


class TestPOMDecay:
    def test_decay_moves_values_toward_zero_log_odds(self, pom, center_event):
        pom.process(center_event)
        log_odds_after_event = pom._data[5, 5]
        assert log_odds_after_event > 0  # sanity: Observation raised it above prior

        far_event = Observation(
            geometry=Point(500015.0, 5200085.0),
            timestamp=110.0,
            confidence=0.5,
        )
        pom.process(far_event)
        # exp(-100/100) ≈ 0.368 → data should have decayed
        expected_after_decay = log_odds_after_event * np.exp(-100.0 / 100.0)
        assert pom._data[5, 5] == pytest.approx(expected_after_decay, rel=1e-6)

    def test_high_confidence_event_raises_probability_above_prior(self, pom, center_event):
        pom.process(center_event)
        assert pom.map.probabilities[5, 5] > pom.prior

    def test_low_confidence_event_lowers_probability_below_prior(self, pom):
        obs = Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.1)
        pom.process(obs)
        assert pom.map.probabilities[5, 5] < pom.prior


class TestPOMReset:
    def test_reset_restores_neutral_state(self, pom, center_event):
        pom.process(center_event)
        pom.reset()
        assert np.allclose(pom._data, 0.0)

    def test_reset_with_custom_prior_restores_neutral_state(self):
        # Prior is a sensor baseline, not occupancy belief — reset always goes to neutral (0.5)
        p = POM(decay_s=100.0, prior=0.7)
        p.configure(CRS, BBOX, RES)
        p.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=0.9))
        p.reset()
        assert np.allclose(p._data, 0.0)

    def test_observation_at_prior_confidence_leaves_map_unchanged(self):
        # confidence == prior → logit(confidence) - logit(prior) = 0 → no update
        p = POM(decay_s=100.0, prior=0.3)
        p.configure(CRS, BBOX, RES)
        p.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=1.0, confidence=0.3))
        assert np.allclose(p._data, 0.0)


class TestPOMConfig:
    def test_get_config_contains_decay_s(self):
        assert POM(decay_s=60.0, prior=0.3).get_config()["decay_s"] == 60.0

    def test_get_config_contains_prior(self):
        assert POM(decay_s=60.0, prior=0.3).get_config()["prior"] == 0.3

    def test_get_config_is_serializable(self):
        import json
        cfg = POM(decay_s=100.0).get_config()
        json.dumps(cfg)  # should not raise
