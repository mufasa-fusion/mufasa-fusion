import threading

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from shapely.geometry import Point

from mufasa import BoundingBox, Observation, Location, Map, Graph
from mufasa.io.inputs.base import InputNode
from mufasa.io.inputs.streaming import LocationStreamingInput, MapStreamingInput
from mufasa.io.outputs.python_object import LocationOutput, MapOutput
from tests.helpers import CRS as TEST_CRS, BBOX, RES


def _map():
    transform = from_bounds(0, 0, 1, 1, 10, 10)
    return Map(np.zeros((10, 10)), transform, CRS.from_epsg(4326))


def _obs(t=1.0):
    return Observation(geometry=Point(0, 0), timestamp=t, confidence=0.9)


# ---------------------------------------------------------------------------
# Types and contracts
# ---------------------------------------------------------------------------

class TestTypes:
    def test_location_output_type(self):
        assert LocationStreamingInput().output_type is Location

    def test_map_output_type(self):
        assert MapStreamingInput().output_type is Map

    def test_input_types_empty(self):
        assert LocationStreamingInput().input_types == frozenset()
        assert MapStreamingInput().input_types == frozenset()

    def test_get_config_empty(self):
        assert LocationStreamingInput().get_config() == {}
        assert MapStreamingInput().get_config() == {}


# ---------------------------------------------------------------------------
# ingest / stop / items
# ---------------------------------------------------------------------------

class TestIngestAndItems:
    def test_single_observation(self):
        src = LocationStreamingInput()
        obs = _obs()
        src.ingest(obs)
        src.stop()
        assert list(src.items()) == [obs]

    def test_multiple_observations_in_order(self):
        src = LocationStreamingInput()
        items = [_obs(t=float(i)) for i in range(5)]
        for item in items:
            src.ingest(item)
        src.stop()
        assert list(src.items()) == items

    def test_single_map(self):
        src = MapStreamingInput()
        m = _map()
        src.ingest(m)
        src.stop()
        assert list(src.items()) == [m]

    def test_stop_before_ingest_yields_nothing(self):
        src = LocationStreamingInput()
        src.stop()
        assert list(src.items()) == []

    def test_ingest_from_background_thread(self):
        src = LocationStreamingInput()
        items = [_obs(t=float(i)) for i in range(10)]

        def producer():
            for item in items:
                src.ingest(item)
            src.stop()

        t = threading.Thread(target=producer)
        t.start()
        received = list(src.items())
        t.join()
        assert received == items

    def test_items_blocks_until_stop(self):
        src = LocationStreamingInput()
        received = []
        ready = threading.Event()

        def consumer():
            ready.set()
            received.extend(src.items())

        t = threading.Thread(target=consumer)
        t.start()
        ready.wait()
        src.ingest(_obs(t=1.0))
        src.ingest(_obs(t=2.0))
        src.stop()
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert len(received) == 2


# ---------------------------------------------------------------------------
# Graph integration
# ---------------------------------------------------------------------------

class TestGraphIntegration:
    _SPATIAL = dict(crs=TEST_CRS, bbox=BoundingBox(14.0, 47.0, 14.1, 47.1), resolution=RES)

    def test_dispatches_observations_to_successor(self):
        src = LocationStreamingInput(); src.name = "src"
        out = LocationOutput()(src);   out.name = "out"
        g = Graph(inputs=[src], outputs=[out], **self._SPATIAL)

        obs = _obs()
        src.ingest(obs)
        src.stop()
        g.run()

        assert g.outputs[0].result == [obs]

    def test_two_streaming_inputs_both_drain(self):
        src_a = LocationStreamingInput(); src_a.name = "a"
        src_b = LocationStreamingInput(); src_b.name = "b"
        out_a = LocationOutput()(src_a);  out_a.name = "out_a"
        out_b = LocationOutput()(src_b);  out_b.name = "out_b"
        g = Graph(inputs=[src_a, src_b], outputs=[out_a, out_b], **self._SPATIAL)

        obs_a = _obs(t=1.0)
        obs_b = _obs(t=2.0)
        src_a.ingest(obs_a); src_a.stop()
        src_b.ingest(obs_b); src_b.stop()
        g.run()

        assert g.outputs[0].result == [obs_a]
        assert g.outputs[1].result == [obs_b]

    def test_mixing_file_and_streaming_raises(self):
        from mufasa.io.inputs.python_object import LocationInput
        file_src   = LocationInput(data=[_obs()])
        stream_src = LocationStreamingInput()
        out = LocationOutput()(file_src, stream_src)
        with pytest.raises(ValueError, match="mix"):
            Graph(inputs=[file_src, stream_src], outputs=[out], **self._SPATIAL)

    def test_graph_stop_signals_all_streaming_inputs(self):
        src = LocationStreamingInput(); src.name = "src"
        out = LocationOutput()(src);   out.name = "out"
        g = Graph(inputs=[src], outputs=[out], **self._SPATIAL)

        finished = threading.Event()

        def run_and_signal():
            g.run()
            finished.set()

        t = threading.Thread(target=run_and_signal)
        t.start()
        g.stop()
        finished.wait(timeout=2.0)
        assert finished.is_set()
