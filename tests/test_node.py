import pytest

from mufasa import Observation, Location, Map, Node
from tests.conftest import (
    LocSink, LocSource, LocToLoc, LocToMap,
    MapSink, MapSource, MapToLoc, MapToMap, MixedToLoc,
)


class TestNodeDefaults:
    def test_input_types_default_empty_for_source(self):
        node = LocSource()
        assert node.input_types == frozenset()

    def test_output_type_default_none_for_sink(self):
        node = LocSink()
        assert node.output_type is None

    def test_predecessors_start_empty(self):
        assert LocSource()._predecessors == []

    def test_successors_start_empty(self):
        assert LocSource()._successors == []

    def test_predecessors_not_shared_between_instances(self):
        a = LocSource()
        b = LocSource()
        a._predecessors.append(object())
        assert b._predecessors == []


class TestNodeWiring:
    def test_call_returns_self(self):
        src = LocSource()
        proc = LocToMap()
        result = proc(src)
        assert result is proc

    def test_predecessor_registered_on_successor(self):
        src = LocSource()
        proc = LocToMap()
        proc(src)
        assert src in proc._predecessors

    def test_successor_registered_on_predecessor(self):
        src = LocSource()
        proc = LocToMap()
        proc(src)
        assert proc in src._successors

    def test_multiple_inputs_all_registered(self):
        src_a = LocSource()
        src_b = LocSource()
        proc = LocToMap()
        proc(src_a, src_b)
        assert src_a in proc._predecessors
        assert src_b in proc._predecessors
        assert proc in src_a._successors
        assert proc in src_b._successors

    def test_chaining_wires_correctly(self):
        src  = LocSource()
        proc = LocToMap()
        sink = MapSink()
        proc(src)
        sink(proc)
        assert src in proc._predecessors
        assert proc in src._successors
        assert proc in sink._predecessors
        assert sink in proc._successors

    def test_one_source_multiple_successors(self):
        src   = LocSource()
        proc1 = LocToMap()
        proc2 = LocToLoc()
        proc1(src)
        proc2(src)
        assert proc1 in src._successors
        assert proc2 in src._successors

    def test_fan_in_multiple_sources_one_successor(self):
        src_a = LocSource()
        src_b = LocSource()
        proc  = LocToMap()
        proc(src_a, src_b)
        assert len(proc._predecessors) == 2

    def test_mixed_input_types_accepted(self):
        loc_src = LocSource()
        map_src = MapSource()
        proc    = MixedToLoc()
        proc(loc_src, map_src)
        assert loc_src in proc._predecessors
        assert map_src in proc._predecessors


class TestConfigure:
    def test_default_configure_is_noop(self):
        LocSource().configure("EPSG:32633", None, (10.0, 10.0))  # should not raise

    def test_configure_can_be_overridden(self):
        received = []
        class N(LocSource):
            def configure(self, crs, bbox, resolution):
                received.append((crs, bbox, resolution))
        N().configure("EPSG:32633", "bbox", (10.0, 10.0))
        assert received == [("EPSG:32633", "bbox", (10.0, 10.0))]


class TestTriggerSuccessors:
    def test_calls_process_on_each_successor(self):
        call_count = []

        class Sink(Node):
            _input_types = [Location]
            _output_type = None
            def process(self, obs=None):
                call_count.append(1)
            def get_config(self): return {}

        src = LocSource()
        s1 = Sink()
        s2 = Sink()
        s1(src)
        s2(src)
        src._trigger_successors()
        assert len(call_count) == 2

    def test_no_successors_does_nothing(self):
        LocSource()._trigger_successors()  # should not raise


class TestNodeTypeValidation:
    def test_correct_type_does_not_raise(self):
        src  = LocSource()
        proc = LocToMap()
        proc(src)  # should not raise

    def test_wrong_output_type_raises_type_error(self):
        map_src = MapSource()
        loc_proc = LocToMap()  # accepts Location, not Map
        with pytest.raises(TypeError):
            loc_proc(map_src)

    def test_sink_used_as_input_raises_type_error(self):
        sink = LocSink()
        proc = LocToLoc()
        with pytest.raises(TypeError):
            proc(sink)

    def test_source_called_with_input_raises_type_error(self):
        src_a = LocSource()
        src_b = LocSource()
        with pytest.raises(TypeError):
            src_a(src_b)

    def test_map_into_loc_accepting_node_raises(self):
        map_src  = MapSource()
        loc_sink = LocSink()
        with pytest.raises(TypeError):
            loc_sink(map_src)

    def test_loc_into_map_accepting_node_raises(self):
        loc_src  = LocSource()
        map_sink = MapSink()
        with pytest.raises(TypeError):
            map_sink(loc_src)

    def test_subclass_output_accepted_by_parent_input_type(self):
        class SubLocation(Location):
            pass

        class SubSource(Node):
            _input_types = []
            _output_type = SubLocation
            def process(self): pass
            def get_config(self): return {}

        proc = LocToMap()
        proc(SubSource())  # should not raise: SubLocation is-a Location

    def test_subclass_output_rejected_by_incompatible_type(self):
        class SubLocation(Location):
            pass

        class SubSource(Node):
            _input_types = []
            _output_type = SubLocation
            def process(self): pass
            def get_config(self): return {}

        with pytest.raises(TypeError):
            MapSink()(SubSource())  # SubLocation is not a Map


class TestNodeClassAttributes:
    def test_input_types_from_class_attribute(self):
        node = LocToMap()
        assert Location in node.input_types

    def test_input_types_empty_for_source(self):
        assert LocSource().input_types == frozenset()

    def test_output_type_from_class_attribute(self):
        assert LocToMap().output_type is Map

    def test_output_type_none_for_sink(self):
        assert LocSink().output_type is None

    def test_mixed_input_types_frozenset(self):
        node = MixedToLoc()
        assert node.input_types == frozenset({Location, Map})

    def test_missing_input_types_raises_on_instantiation(self):
        class Incomplete(Node):
            _output_type = Location
            def process(self): pass
            def get_config(self): return {}
        with pytest.raises(TypeError):
            Incomplete()

    def test_missing_output_type_raises_on_instantiation(self):
        class Incomplete(Node):
            _input_types = [Location]
            def process(self): pass
            def get_config(self): return {}
        with pytest.raises(TypeError):
            Incomplete()


class TestNodeLifecycleMethods:
    """flush() and reset() are no-ops on Node; stateful nodes override them."""

    def _make_node(self):
        class N(Node):
            _input_types = [Location]
            _output_type = Map
            def process(self, obs=None): pass
            def get_config(self): return {}
        return N()

    def test_flush_is_callable_by_default(self):
        self._make_node().flush()  # must not raise

    def test_reset_is_callable_by_default(self):
        self._make_node().reset()  # must not raise

    def test_flush_can_be_overridden(self):
        sentinel = object()
        class N(Node):
            _input_types = [Location]
            _output_type = Map
            def process(self, obs=None): pass
            def get_config(self): return {}
            def flush(self): return sentinel
        assert N().flush() is sentinel

    def test_reset_can_be_overridden(self):
        sentinel = object()
        class N(Node):
            _input_types = [Location]
            _output_type = Map
            def process(self, obs=None): pass
            def get_config(self): return {}
            def reset(self): return sentinel
        assert N().reset() is sentinel
