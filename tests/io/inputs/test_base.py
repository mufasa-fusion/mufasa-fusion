import pytest

from mufasa import Observation, Location, Map
from mufasa.node import Node
from mufasa.io.inputs.base import InputNode
from mufasa.io.inputs.streaming import StreamingInputNode, LocationStreamingInput, MapStreamingInput


class TestInputNodeTypes:
    def test_location_input_output_type(self):
        class ConcreteInput(InputNode):
            _output_type = Location
            def items(self): return []
            def get_config(self): return {}
        assert ConcreteInput().output_type is Location

    def test_map_input_output_type(self):
        class ConcreteInput(InputNode):
            _output_type = Map
            def items(self): return []
            def get_config(self): return {}
        assert ConcreteInput().output_type is Map

    def test_input_types_is_empty(self):
        class ConcreteInput(InputNode):
            _output_type = Location
            def items(self): return []
            def get_config(self): return {}
        assert ConcreteInput().input_types == frozenset()

    def test_items_abstract_prevents_instantiation(self):
        class BareInput(InputNode):
            _output_type = Location
            def get_config(self): return {}
        with pytest.raises(TypeError):
            BareInput()


class TestInputNodeRun:
    def test_run_dispatches_observations_to_successors(self):
        obs = Observation(geometry=None, timestamp=1.0)

        class Source(InputNode):
            _output_type = Observation
            def items(self): return [obs]
            def get_config(self): return {}

        received = []

        class Sink(Node):
            _output_type = None
            _input_types = [Observation]
            def process(self, item): received.append(item)
            def get_config(self): return {}

        src = Source()
        sink = Sink()
        src._successors.append(sink)
        src.configure(None, None, None)
        src.run()
        assert received == [obs]

    def test_run_dispatches_maps_without_args(self):
        from shapely.affinity import affine_transform
        import numpy as np
        from rasterio.transform import from_bounds
        from rasterio.crs import CRS

        transform = from_bounds(0, 0, 1, 1, 10, 10)
        crs = CRS.from_epsg(4326)
        m = Map(np.zeros((10, 10)), transform, crs)

        class Source(InputNode):
            _output_type = Map
            def items(self): return [m]
            def get_config(self): return {}

        called = []

        class Sink(Node):
            _output_type = None
            _input_types = [Map]
            def process(self): called.append(True)
            def get_config(self): return {}

        src = Source()
        sink = Sink()
        src._successors.append(sink)
        src.configure(None, None, None)
        src.run()
        assert called == [True]
        assert src.map is m


class TestStreamingInputNode:
    def test_location_streaming_input_output_type(self):
        assert LocationStreamingInput().output_type is Location

    def test_map_streaming_input_output_type(self):
        assert MapStreamingInput().output_type is Map

    def test_ingest_makes_location_available_via_items(self):
        obs = Observation(geometry=None, timestamp=1.0)
        src = LocationStreamingInput()
        src.ingest(obs)
        src.stop()
        assert list(src.items()) == [obs]

    def test_ingest_map_available_via_items(self):
        import numpy as np
        from rasterio.transform import from_bounds
        from rasterio.crs import CRS

        transform = from_bounds(0, 0, 1, 1, 10, 10)
        m = Map(np.zeros((10, 10)), transform, CRS.from_epsg(4326))
        src = MapStreamingInput()
        src.ingest(m)
        src.stop()
        assert list(src.items()) == [m]

    def test_get_config_returns_empty_dict(self):
        assert LocationStreamingInput().get_config() == {}
        assert MapStreamingInput().get_config() == {}
