from mufasa import Observation, Location, Map
from mufasa.io.outputs.base import OutputNode
from mufasa.io.outputs.streaming import StreamingOutputNode


class TestOutputNodeTypes:
    def test_location_output_input_types(self):
        class ConcreteOutput(OutputNode):
            _input_types = [Location]
            def process(self, obs=None): pass
            def get_config(self): return {}
        assert Location in ConcreteOutput().input_types

    def test_map_output_input_types(self):
        class ConcreteOutput(OutputNode):
            _input_types = [Map]
            def process(self): pass
            def get_config(self): return {}
        assert Map in ConcreteOutput().input_types

    def test_output_type_is_none(self):
        class ConcreteOutput(OutputNode):
            _input_types = [Location]
            def process(self, obs=None): pass
            def get_config(self): return {}
        assert ConcreteOutput().output_type is None

    def test_save_is_noop_by_default(self):
        class ConcreteOutput(OutputNode):
            _input_types = [Location]
            def process(self, obs=None): pass
            def get_config(self): return {}
        ConcreteOutput().save()  # must not raise


class TestStreamingOutputNode:
    def test_default_input_type_is_location(self):
        assert Location in StreamingOutputNode().input_types

    def test_callback_passed_at_construction(self):
        received = []
        node = StreamingOutputNode(received.append)
        obs = Observation(geometry=None, timestamp=1.0)
        node.process(obs)
        assert received == [obs]

    def test_callback_reassignable_after_construction(self):
        received = []
        node = StreamingOutputNode()
        node.on_output = received.append
        obs = Observation(geometry=None, timestamp=1.0)
        node.process(obs)
        assert received == [obs]

    def test_no_callback_does_not_raise(self):
        node = StreamingOutputNode()
        node.process(Observation(geometry=None, timestamp=1.0))

    def test_get_config_returns_empty_dict(self):
        assert StreamingOutputNode().get_config() == {}
