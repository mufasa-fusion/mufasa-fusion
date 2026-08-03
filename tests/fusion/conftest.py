"""Shared fixtures for fusion tests: two configured POMs with events processed."""
import pytest
from shapely.geometry import Point

from mufasa import Observation
from mufasa.nodes.mapping import POM
from tests.helpers import CRS, BBOX, RES, CENTRE_X, CENTRE_Y


@pytest.fixture
def pom_a():
    p = POM(decay_s=100.0, prior=0.5)
    p.configure(CRS, BBOX, RES)
    p.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.9))
    return p


@pytest.fixture
def pom_b():
    p = POM(decay_s=100.0, prior=0.5)
    p.configure(CRS, BBOX, RES)
    p.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.8))
    return p


@pytest.fixture
def pom_low():
    """POM with a low-confidence Observation at centre — probability below prior."""
    p = POM(decay_s=100.0, prior=0.5)
    p.configure(CRS, BBOX, RES)
    p.process(Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=10.0, confidence=0.1))
    return p
