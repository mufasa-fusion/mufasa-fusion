import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be set before pyplot import

import warnings
import numpy as np

import pytest
from shapely.geometry import Point

from mufasa import BoundingBox, Observation, Location, Map, Graph, Node
from mufasa.graph import _node_depths
from mufasa.io.inputs.python_object import LocationInput
from mufasa.io.outputs.python_object import LocationOutput, MapOutput
from tests.conftest import (
    LocSink, LocSource, LocToLoc, LocToMap,
    MapSink, MapSource, MapToLoc, MapToMap, MixedToLoc,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def linear_pipeline():
    """LocSource → LocToMap → MapSink"""
    src  = LocSource()
    proc = LocToMap()(src)
    sink = MapSink()(proc)
    return src, sink


# ---------------------------------------------------------------------------
# Valid pipelines
# ---------------------------------------------------------------------------

class TestValidPipelines:
    def test_simple_linear_pipeline(self, spatial):
        src, sink = linear_pipeline()
        Graph(inputs=[src], outputs=[sink], **spatial)

    def test_trivial_single_node_is_both_input_and_output(self, spatial):
        src = LocSource()
        Graph(inputs=[src], outputs=[src], **spatial)

    def test_fan_in_two_sources_one_sink(self, spatial):
        src_a = LocSource()
        src_b = LocSource()
        proc  = LocToMap()(src_a, src_b)
        sink  = MapSink()(proc)
        Graph(inputs=[src_a, src_b], outputs=[sink], **spatial)

    def test_fan_out_one_source_two_sinks(self, spatial):
        src   = LocSource()
        sink1 = MapSink()(LocToMap()(src))
        sink2 = LocSink()(LocToLoc()(src))
        Graph(inputs=[src], outputs=[sink1, sink2], **spatial)

    def test_diamond_topology(self, spatial):
        # src → proc_a ↘
        #            fuse → sink
        # src → proc_b ↗
        src    = LocSource()
        proc_a = LocToMap()(src)
        proc_b = LocToMap()(src)
        fused  = MapToMap()(proc_a, proc_b)
        sink   = MapSink()(fused)
        Graph(inputs=[src], outputs=[sink], **spatial)

    def test_deep_chain(self, spatial):
        src = LocSource()
        node = src
        for _ in range(10):
            node = LocToLoc()(node)
        sink = LocSink()(node)
        Graph(inputs=[src], outputs=[sink], **spatial)

    def test_multiple_independent_chains(self, spatial):
        src1  = LocSource()
        sink1 = MapSink()(LocToMap()(src1))

        src2  = MapSource()
        sink2 = MapSink()(MapToMap()(src2))

        Graph(inputs=[src1, src2], outputs=[sink1, sink2], **spatial)

    def test_mixed_input_type_node(self, spatial):
        loc_src = LocSource()
        map_src = MapSource()
        proc    = MixedToLoc()(loc_src, map_src)
        sink    = LocSink()(proc)
        Graph(inputs=[loc_src, map_src], outputs=[sink], **spatial)

    def test_intermediate_node_used_as_output(self, spatial):
        src  = LocSource()
        proc = LocToMap()(src)
        Graph(inputs=[src], outputs=[proc], **spatial)


# ---------------------------------------------------------------------------
# Optional spatial parameters
# ---------------------------------------------------------------------------

class TestOptionalSpatialParams:
    def test_event_only_pipeline_without_spatial_does_not_raise(self):
        src  = LocSource()
        sink = LocSink()(src)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink])  # no crs / bbox / resolution

    def test_no_crs_emits_warning(self):
        src  = LocSource()
        sink = LocSink()(src)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink])
        crs_warns = [x for x in w if "crs" in str(x.message).lower() or "cartesian" in str(x.message).lower()]
        assert len(crs_warns) == 1

    def test_no_crs_warning_message_mentions_metres(self):
        src  = LocSource()
        sink = LocSink()(src)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink])
        msg = str(w[0].message)
        assert "metre" in msg.lower()

    def test_no_crs_with_wgs84_bbox_suggests_utm(self):
        src  = LocSource()
        sink = LocSink()(src)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink], bbox=BoundingBox(14.0, 47.0, 14.2, 47.2))
        msg = str(w[0].message)
        assert "EPSG:32633" in msg

    def test_no_crs_with_projected_bbox_no_utm_suggestion(self):
        src  = LocSource()
        sink = LocSink()(src)
        # UTM-metre coordinates — outside WGS84 degree range
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink], bbox=BoundingBox(500000.0, 5200000.0, 510000.0, 5210000.0))
        msg = str(w[0].message)
        assert "EPSG:" not in msg

    def test_no_crs_no_bbox_no_utm_suggestion(self):
        src  = LocSource()
        sink = LocSink()(src)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink])
        msg = str(w[0].message)
        assert "EPSG:" not in msg

    def test_crs_provided_no_crs_warning(self, spatial):
        src, sink = linear_pipeline()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink], **spatial)
        crs_warns = [x for x in w if "cartesian" in str(x.message).lower()]
        assert crs_warns == []

    def test_map_pipeline_without_bbox_raises(self, spatial):
        src, sink = linear_pipeline()
        no_bbox = {k: v for k, v in spatial.items() if k != "bbox"}
        with pytest.raises(ValueError, match="bbox"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                Graph(inputs=[src], outputs=[sink], **no_bbox)

    def test_map_pipeline_without_resolution_raises(self, spatial):
        src, sink = linear_pipeline()
        no_res = {k: v for k, v in spatial.items() if k != "resolution"}
        with pytest.raises(ValueError, match="resolution"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                Graph(inputs=[src], outputs=[sink], **no_res)

    def test_map_pipeline_error_names_the_offending_nodes(self, spatial):
        src, sink = linear_pipeline()
        no_bbox = {k: v for k, v in spatial.items() if k != "bbox"}
        with pytest.raises(ValueError, match="LocToMap|MapSink"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                Graph(inputs=[src], outputs=[sink], **no_bbox)

    def test_map_subclass_pipeline_without_bbox_raises(self, spatial):
        from mufasa.io.inputs.base import InputNode

        class MapSubclass(Map):
            pass

        class SubclassSource(InputNode):
            _output_type = MapSubclass
            def items(self): return []
            def get_config(self): return {}

        class SubclassSink(Node):
            _input_types = [MapSubclass]
            _output_type = None
            def process(self): pass
            def get_config(self): return {}

        src  = SubclassSource()
        sink = SubclassSink()(src)
        no_bbox = {k: v for k, v in spatial.items() if k != "bbox"}
        with pytest.raises(ValueError, match="bbox"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                Graph(inputs=[src], outputs=[sink], **no_bbox)


# ---------------------------------------------------------------------------
# Pixel count warning
# ---------------------------------------------------------------------------

class TestPixelCountWarning:
    def test_no_warning_within_limit(self, spatial):
        src, sink = linear_pipeline()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink], **spatial)
        pixel_warns = [x for x in w if "pixel" in str(x.message).lower()]
        assert pixel_warns == []

    def test_warning_raised_above_limit(self, spatial):
        # resolution (1, 1) on the default bbox produces ~83 M pixels
        src, sink = linear_pipeline()
        fine = dict(spatial, resolution=(1.0, 1.0))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink], **fine)
        pixel_warns = [x for x in w if "pixel" in str(x.message).lower()]
        assert len(pixel_warns) == 1

    def test_warning_message_contains_dimensions(self, spatial):
        src, sink = linear_pipeline()
        fine = dict(spatial, resolution=(1.0, 1.0))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Graph(inputs=[src], outputs=[sink], **fine)
        msg = str(w[0].message)
        assert "pixel" in msg.lower()
        assert "×" in msg


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    def test_simple_two_node_cycle(self, spatial):
        proc_a = LocToLoc()
        proc_b = LocToLoc()
        # manually create a cycle bypassing __call__ type checks
        proc_a._successors.append(proc_b)
        proc_b._predecessors.append(proc_a)
        proc_b._successors.append(proc_a)
        proc_a._predecessors.append(proc_b)

        src  = LocSource()
        src._successors.append(proc_a)
        proc_a._predecessors.insert(0, src)

        with pytest.raises(ValueError, match="[Cc]ycle"):
            Graph(inputs=[src], outputs=[], **spatial)

    def test_three_node_cycle(self, spatial):
        a = LocToLoc()
        b = LocToLoc()
        c = LocToLoc()

        src = LocSource()
        src._successors.append(a)
        a._predecessors.append(src)

        # a → b → c → a
        for pred, succ in [(a, b), (b, c), (c, a)]:
            pred._successors.append(succ)
            succ._predecessors.append(pred)

        with pytest.raises(ValueError, match="[Cc]ycle"):
            Graph(inputs=[src], outputs=[], **spatial)

    def test_self_loop_via_manual_wiring(self, spatial):
        proc = LocToLoc()
        src  = LocSource()
        src._successors.append(proc)
        proc._predecessors.append(src)
        # proc points to itself
        proc._successors.append(proc)
        proc._predecessors.append(proc)

        with pytest.raises(ValueError, match="[Cc]ycle"):
            Graph(inputs=[src], outputs=[], **spatial)


# ---------------------------------------------------------------------------
# Output reachability
# ---------------------------------------------------------------------------

class TestOutputReachability:
    def test_output_not_connected_to_any_input_raises(self, spatial):
        src  = LocSource()
        proc = LocToMap()(src)
        sink = MapSink()(proc)

        orphan_sink = MapSink()  # completely disconnected

        with pytest.raises(ValueError, match="not reachable"):
            Graph(inputs=[src], outputs=[sink, orphan_sink], **spatial)

    def test_output_on_separate_unconnected_graph_raises(self, spatial):
        src1  = LocSource()
        sink1 = MapSink()(LocToMap()(src1))

        src2  = LocSource()
        sink2 = MapSink()(LocToMap()(src2))

        # only src1 declared as input, but sink2 belongs to src2's graph
        with pytest.raises(ValueError, match="not reachable"):
            Graph(inputs=[src1], outputs=[sink1, sink2], **spatial)

    def test_output_is_ancestor_of_declared_input_raises(self, spatial):
        src  = LocSource()
        proc = LocToMap()(src)
        _    = MapSink()(proc)

        # src is upstream of proc; declaring src as output of itself is fine,
        # but declaring an unrelated node fails
        orphan = LocSource()
        with pytest.raises(ValueError, match="not reachable"):
            Graph(inputs=[src], outputs=[orphan], **spatial)


# ---------------------------------------------------------------------------
# Dangling sinks (undeclared terminal nodes)
# ---------------------------------------------------------------------------

class TestDanglingSinks:
    def test_undeclared_sink_raises(self, spatial):
        src         = LocSource()
        proc        = LocToMap()(src)
        proper_sink = MapSink()(proc)

        # create a second branch that dead-ends without being declared
        dangling = MapSink()(proc)

        with pytest.raises(ValueError, match="not declared as an output"):
            Graph(inputs=[src], outputs=[proper_sink], **spatial)

    def test_processing_node_with_no_successor_not_declared_raises(self, spatial):
        src  = LocSource()
        proc = LocToMap()(src)
        # proc has no successors and is not declared as an output

        with pytest.raises(ValueError, match="not declared as an output"):
            Graph(inputs=[src], outputs=[], **spatial)

    def test_all_sinks_declared_passes(self, spatial):
        src    = LocSource()
        proc   = LocToMap()(src)
        sink_a = MapSink()(proc)
        sink_b = MapSink()(proc)
        Graph(inputs=[src], outputs=[sink_a, sink_b], **spatial)

    def test_intermediate_branch_dead_end_raises(self, spatial):
        src       = LocSource()
        main_proc = LocToMap()(src)
        main_sink = MapSink()(main_proc)

        # side branch off src that terminates without declaration
        LocSink()(LocToLoc()(src))

        with pytest.raises(ValueError, match="not declared as an output"):
            Graph(inputs=[src], outputs=[main_sink], **spatial)


# ---------------------------------------------------------------------------
# Undeclared sources
# ---------------------------------------------------------------------------

class TestUndeclaredSources:
    def test_source_node_wired_but_not_in_inputs_raises(self, spatial):
        src      = LocSource()
        proc     = LocToMap()(src)
        sink     = MapSink()(proc)
        floating = MapSource()
        # manually wire floating into proc without declaring it
        floating._successors.append(proc)
        proc._predecessors.append(floating)
        with pytest.raises(ValueError, match="not declared as an input"):
            Graph(inputs=[src], outputs=[sink], **spatial)

    def test_static_map_not_in_inputs_raises(self, spatial):
        """Static map source wired to fusion node but omitted from g.inputs."""
        event_src = LocSource()
        static    = MapSource()
        pom       = LocToMap()(event_src)
        fused     = MapToMap()(pom, static)
        sink      = MapSink()(fused)
        with pytest.raises(ValueError, match="not declared as an input"):
            Graph(inputs=[event_src], outputs=[sink], **spatial)

    def test_static_map_in_inputs_passes(self, spatial):
        """Same graph as above but static declared — should be valid."""
        event_src = LocSource()
        static    = MapSource()
        pom       = LocToMap()(event_src)
        fused     = MapToMap()(pom, static)
        sink      = MapSink()(fused)
        Graph(inputs=[event_src, static], outputs=[sink], **spatial)

    def test_two_independent_undeclared_sources_raises(self, spatial):
        src_a  = LocSource()
        src_b  = LocSource()
        proc   = LocToMap()(src_a, src_b)
        sink   = MapSink()(proc)
        with pytest.raises(ValueError, match="not declared as an input"):
            Graph(inputs=[src_a], outputs=[sink], **spatial)


# ---------------------------------------------------------------------------
# _all_nodes
# ---------------------------------------------------------------------------

class TestAllNodes:
    def test_linear_pipeline_contains_all_nodes(self, spatial):
        src, sink = linear_pipeline()
        proc = src._successors[0]
        g = Graph(inputs=[src], outputs=[sink], **spatial)
        nodes = g._all_nodes()
        assert src in nodes
        assert proc in nodes
        assert sink in nodes

    def test_topological_order_predecessors_before_successors(self, spatial):
        src, sink = linear_pipeline()
        proc = src._successors[0]
        nodes = Graph(inputs=[src], outputs=[sink], **spatial)._all_nodes()
        assert nodes.index(src) < nodes.index(proc) < nodes.index(sink)

    def test_diamond_topology_all_nodes_present(self, spatial):
        src    = LocSource()
        proc_a = LocToMap()(src)
        proc_b = LocToMap()(src)
        fused  = MapToMap()(proc_a, proc_b)
        sink   = MapSink()(fused)
        nodes  = Graph(inputs=[src], outputs=[sink], **spatial)._all_nodes()
        assert all(n in nodes for n in [src, proc_a, proc_b, fused, sink])

    def test_source_before_all_processing_nodes(self, spatial):
        src    = LocSource()
        proc_a = LocToMap()(src)
        proc_b = LocToMap()(src)
        fused  = MapToMap()(proc_a, proc_b)
        sink   = MapSink()(fused)
        nodes  = Graph(inputs=[src], outputs=[sink], **spatial)._all_nodes()
        assert nodes.index(src) < nodes.index(proc_a)
        assert nodes.index(src) < nodes.index(proc_b)

    def test_no_duplicates(self, spatial):
        src, sink = linear_pipeline()
        nodes = Graph(inputs=[src], outputs=[sink], **spatial)._all_nodes()
        assert len(nodes) == len(set(id(n) for n in nodes))


# ---------------------------------------------------------------------------
# _configure_nodes
# ---------------------------------------------------------------------------

class TestConfigureNodes:
    def test_configure_called_on_all_nodes_at_init(self, spatial):
        calls = []

        class RecordingNode(LocToMap):
            def configure(self, crs, bbox, resolution):
                calls.append(crs)

        src  = LocSource()
        proc = RecordingNode()(src)
        sink = MapSink()(proc)
        Graph(inputs=[src], outputs=[sink], **spatial)

        assert len(calls) == 1
        assert calls[0] == spatial["crs"]

    def test_configure_receives_projected_bbox_not_wgs84(self, spatial):
        received = []

        class RecordingNode(LocToMap):
            def configure(self, crs, bbox, resolution):
                received.append(bbox)

        src  = LocSource()
        proc = RecordingNode()(src)
        sink = MapSink()(proc)
        Graph(inputs=[src], outputs=[sink], **spatial)

        assert received[0] != spatial["bbox"]      # not WGS84
        assert abs(received[0].min_x) > 100        # UTM coords are in metres

    def test_configure_called_on_every_node_in_pipeline(self, spatial):  # noqa: F811
        calls = []

        class RecordingLocToMap(LocToMap):
            def configure(self, crs, bbox, resolution):
                calls.append(id(self))

        class RecordingMapToMap(MapToMap):
            def configure(self, crs, bbox, resolution):
                calls.append(id(self))

        src   = LocSource()
        proc1 = RecordingLocToMap()(src)
        proc2 = RecordingMapToMap()(proc1)
        sink  = MapSink()(proc2)
        Graph(inputs=[src], outputs=[sink], **spatial)

        assert len(calls) == 2


# ---------------------------------------------------------------------------
# _node_depths
# ---------------------------------------------------------------------------

class TestNodeDepths:
    def test_linear_pipeline_depths(self, spatial):
        src, sink = linear_pipeline()
        proc = src._successors[0]
        g = Graph(inputs=[src], outputs=[sink], **spatial)
        depths = _node_depths(g.nodes)
        assert depths[src]  == 0
        assert depths[proc] == 1
        assert depths[sink] == 2

    def test_diamond_merge_depth(self, spatial):
        src    = LocSource()
        proc_a = LocToMap()(src)
        proc_b = LocToMap()(src)
        fused  = MapToMap()(proc_a, proc_b)
        sink   = MapSink()(fused)
        g = Graph(inputs=[src], outputs=[sink], **spatial)
        depths = _node_depths(g.nodes)
        assert depths[src]    == 0
        assert depths[proc_a] == 1
        assert depths[proc_b] == 1
        assert depths[fused]  == 2
        assert depths[sink]   == 3

    def test_static_source_placed_before_first_use_not_at_zero(self, spatial):
        # hist_traffic feeds only into fused (depth 2), so it should sit at depth 1
        # rather than depth 0, avoiding a long backward-looking arrow.
        event_src   = LocSource()
        static      = MapSource()
        pom         = LocToMap()(event_src)       # depth 1
        fused       = MapToMap()(pom, static)     # depth 2
        sink        = MapSink()(fused)
        g = Graph(inputs=[event_src, static], outputs=[sink], **spatial)
        depths = _node_depths(g.nodes)
        assert depths[event_src] == 0
        assert depths[static]    == 1   # one before fused, not forced to 0
        assert depths[pom]       == 1
        assert depths[fused]     == 2
        assert depths[sink]      == 3

    def test_source_with_early_successor_stays_at_zero(self, spatial):
        # A source whose successor is at depth 1 should still land at depth 0.
        src_a  = LocSource()
        src_b  = MapSource()
        proc   = MixedToLoc()(src_a, src_b)
        sink   = LocSink()(proc)
        g = Graph(inputs=[src_a, src_b], outputs=[sink], **spatial)
        depths = _node_depths(g.nodes)
        assert depths[src_a] == 0
        assert depths[src_b] == 0

    def test_two_independent_sources_same_depth(self, spatial):
        src_a  = LocSource()
        src_b  = MapSource()
        proc   = MixedToLoc()(src_a, src_b)
        sink   = LocSink()(proc)
        g = Graph(inputs=[src_a, src_b], outputs=[sink], **spatial)
        depths = _node_depths(g.nodes)
        assert depths[src_a] == 0
        assert depths[src_b] == 0
        assert depths[proc]  == 1


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_does_not_raise(self, spatial, capsys):
        src, sink = linear_pipeline()
        Graph(inputs=[src], outputs=[sink], **spatial).summary()

    def test_summary_contains_crs(self, spatial, capsys):
        src, sink = linear_pipeline()
        Graph(inputs=[src], outputs=[sink], **spatial).summary()
        assert spatial["crs"] in capsys.readouterr().out

    def test_summary_marks_input_and_output_nodes(self, spatial, capsys):
        src, sink = linear_pipeline()
        Graph(inputs=[src], outputs=[sink], **spatial).summary()
        out = capsys.readouterr().out
        assert "[in]"  in out
        assert "[out]" in out

    def test_summary_contains_all_node_names(self, spatial, capsys):
        src, sink = linear_pipeline()
        proc = src._successors[0]
        Graph(inputs=[src], outputs=[sink], **spatial).summary()
        out = capsys.readouterr().out
        for node in [src, proc, sink]:
            assert node.name in out

    def test_summary_shows_predecessor_indices(self, spatial, capsys):
        src, sink = linear_pipeline()
        Graph(inputs=[src], outputs=[sink], **spatial).summary()
        out = capsys.readouterr().out
        assert "Inputs" in out
        assert "0" in out  # predecessor index appears in Inputs column


# ---------------------------------------------------------------------------
# plot_graph
# ---------------------------------------------------------------------------

class TestPlotGraph:
    def test_returns_matplotlib_figure(self, spatial):
        import matplotlib.figure
        src, sink = linear_pipeline()
        fig = Graph(inputs=[src], outputs=[sink], **spatial).plot_graph()
        assert isinstance(fig, matplotlib.figure.Figure)
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_does_not_raise_for_diamond(self, spatial):
        import matplotlib.pyplot as plt
        src    = LocSource()
        proc_a = LocToMap()(src)
        proc_b = LocToMap()(src)
        fused  = MapToMap()(proc_a, proc_b)
        sink   = MapSink()(fused)
        fig = Graph(inputs=[src], outputs=[sink], **spatial).plot_graph()
        plt.close(fig)

    def test_figure_has_expected_patch_count(self, spatial):
        """One patch per node plus legend patches."""
        import matplotlib.pyplot as plt
        src, sink = linear_pipeline()
        fig = Graph(inputs=[src], outputs=[sink], **spatial).plot_graph()
        ax = fig.axes[0]
        n_nodes = 3  # src, proc, sink
        assert len(ax.patches) >= n_nodes
        plt.close(fig)


# ---------------------------------------------------------------------------
# run() — batch temporal ordering
# ---------------------------------------------------------------------------

class _RecordingSink(Node):
    """Sink that records the timestamp of every Observation it receives."""

    _input_types = [Location]
    _output_type = None

    def __init__(self):
        super().__init__()
        self.timestamps: list[float] = []

    def process(self, item) -> None:
        self.timestamps.append(item.timestamp)

    def save(self) -> None:
        pass

    def get_config(self) -> dict:
        return {}


class TestModelRun:

    def test_run_batch_dispatches_in_global_timestamp_order(self, spatial):
        """Two LocationInput nodes with interleaved timestamps: events must arrive
        at the shared downstream sink in merged (ascending) timestamp order — the
        k-way merge in Graph._run_batch() guarantees this."""
        events_a = [
            Observation(geometry=Point(0, 0), timestamp=1.0),
            Observation(geometry=Point(0, 0), timestamp=3.0),
            Observation(geometry=Point(0, 0), timestamp=5.0),
        ]
        events_b = [
            Observation(geometry=Point(0, 0), timestamp=2.0),
            Observation(geometry=Point(0, 0), timestamp=4.0),
        ]

        src_a = LocationInput(events_a)
        src_b = LocationInput(events_b)

        sink = _RecordingSink()(src_a, src_b)

        g = Graph(inputs=[src_a, src_b], outputs=[sink], **spatial)
        g.run()

        assert sink.timestamps == sorted(sink.timestamps)
        assert sink.timestamps == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_run_batch_single_input_dispatches_all_events(self, spatial):
        events = [
            Observation(geometry=Point(0, 0), timestamp=float(i))
            for i in range(5)
        ]
        src  = LocationInput(events)
        sink = _RecordingSink()(src)
        Graph(inputs=[src], outputs=[sink], **spatial).run()

        assert len(sink.timestamps) == 5
        assert sink.timestamps == sorted(sink.timestamps)

    def test_run_batch_empty_second_input_still_dispatches_first(self, spatial):
        """One source with events, one with a single item — all events dispatched."""
        events_a = [Observation(geometry=Point(0, 0), timestamp=float(i)) for i in range(3)]
        events_b = [Observation(geometry=Point(0, 0), timestamp=1.5)]

        src_a = LocationInput(events_a)
        src_b = LocationInput(events_b)

        sink_a = _RecordingSink()(src_a)
        sink_b = _RecordingSink()(src_b)

        Graph(inputs=[src_a, src_b], outputs=[sink_a, sink_b], **spatial).run()

        assert len(sink_a.timestamps) == 3
        assert len(sink_b.timestamps) == 1


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

class TestModelReset:
    def _simple_model(self, spatial):
        """LocationInput → LocationOutput pipeline with one Observation."""
        events = [Observation(geometry=Point(0, 0), timestamp=1.0)]
        src = LocationInput(events)
        out = LocationOutput()(src)
        g = Graph(inputs=[src], outputs=[out], **spatial)
        return Graph, out

    def test_reset_clears_location_output(self, spatial):
        events = [Observation(geometry=Point(0, 0), timestamp=1.0),
                  Observation(geometry=Point(0, 0), timestamp=2.0)]
        src = LocationInput(events)
        out = LocationOutput()(src)
        g = Graph(inputs=[src], outputs=[out], **spatial)
        g.run()
        assert len(out.result) == 2
        g.reset()
        assert out.result == []

    def test_run_twice_with_reset_gives_same_count(self, spatial):
        events = [Observation(geometry=Point(0, 0), timestamp=1.0)]
        src = LocationInput(events)
        out = LocationOutput()(src)
        g = Graph(inputs=[src], outputs=[out], **spatial)
        g.run()
        g.reset()
        g.run()
        assert len(out.result) == 1

    def test_reset_clears_map_output_snapshots(self, spatial):
        from mufasa.nodes.mapping import POM
        from mufasa.nodes.fusion import BayesianFusion

        bb = spatial["bbox"]  # WGS84 degrees; input node reprojects to pipeline CRS
        cx, cy = (bb.min_x + bb.max_x) / 2, (bb.min_y + bb.max_y) / 2
        events = [Observation(geometry=Point(cx, cy), timestamp=1.0, confidence=0.9)]

        src    = LocationInput(events)
        pom    = POM(decay_s=100.0)(src)
        fusion = BayesianFusion()(pom)
        out    = MapOutput(snapshot_interval_s=0.0)(fusion)
        g = Graph(inputs=[src], outputs=[out], **spatial)
        g.run()
        assert len(out.result) >= 1
        g.reset()
        assert out.result == []

    def test_reset_clears_fusion_node_map(self, spatial):
        from pyproj import Transformer
        from mufasa.nodes.mapping import POM
        from mufasa.nodes.fusion import BayesianFusion
        from mufasa.map import Map

        # Derive an event coordinate that falls inside the projected bbox.
        bb = spatial["bbox"]  # WGS84 degrees; input node reprojects to pipeline CRS
        cx, cy = (bb.min_x + bb.max_x) / 2, (bb.min_y + bb.max_y) / 2
        events = [Observation(geometry=Point(cx, cy), timestamp=1.0, confidence=0.9)]

        src    = LocationInput(events)
        pom    = POM(decay_s=100.0)(src)
        fusion = BayesianFusion()(pom)
        out    = MapOutput(snapshot_interval_s=0.0)(fusion)
        g = Graph(inputs=[src], outputs=[out], **spatial)

        g.run()
        assert np.any(fusion.map.data != 0.0)  # data updated after run
        g.reset()
        assert isinstance(fusion.map, Map)     # map still accessible after reset
        assert fusion.map.timestamp == 0.0      # timestamp reset to default
        assert np.all(fusion.map.data == 0.0)  # data zeroed back to initial state

    def test_reset_clears_pom_timestamp(self, spatial):
        """HeatMap.reset() zeroes map.timestamp — verifiable without coordinate maths."""
        from mufasa.nodes.mapping import POM

        bb = spatial["bbox"]  # WGS84 degrees
        cx, cy = (bb.min_x + bb.max_x) / 2, (bb.min_y + bb.max_y) / 2
        events = [Observation(geometry=Point(cx, cy), timestamp=42.0, confidence=0.9)]

        src   = LocationInput(events)
        pom   = POM(decay_s=100.0)(src)
        out   = MapOutput(snapshot_interval_s=0.0)(pom)
        g = Graph(inputs=[src], outputs=[out], **spatial)

        g.run()
        assert pom.map.timestamp == pytest.approx(42.0)  # Observation was processed
        g.reset()
        assert pom.map.timestamp == 0.0                   # reset to default


# ---------------------------------------------------------------------------
# Proxy handling (_SourceProxy inserted by Visualization for Location preds)
# ---------------------------------------------------------------------------

class TestProxyHandling:
    """Graph traversal must treat _SourceProxy as transparent.

    Visualization inserts a _SourceProxy between a Location predecessor and
    itself so it can identify which predecessor an event came from.  The graph
    must treat the proxy as invisible: it should not appear in _all_nodes(),
    should not count as a dangling sink, should not count as an undeclared
    source, and depth/arrow logic must route through it correctly.
    """

    def _build(self, spatial):
        """LocSource → LocToMap(Map) → MapToLoc(Loc) → [proxy] → Visualization.

        Also wires LocToMap directly to Visualization (Map predecessor, no proxy).
        Gives one Map predecessor and one Location predecessor to Visualization.
        """
        from mufasa.io.outputs.visualization import Visualization

        src    = LocSource()
        to_map = LocToMap()(src)    # Location → Map
        to_loc = MapToLoc()(to_map) # Map       → Location
        viz    = Visualization()(to_map, to_loc)
        g      = Graph(inputs=[src], outputs=[viz], **spatial)
        return g, src, to_map, to_loc, viz

    def test_graph_validates_without_error(self, spatial):
        self._build(spatial)

    def test_all_nodes_excludes_proxy(self, spatial):
        from mufasa.io.outputs.visualization import _SourceProxy
        g, *_ = self._build(spatial)
        for node in g._all_nodes():
            assert not isinstance(node, _SourceProxy)

    def test_all_nodes_count_matches_real_node_count(self, spatial):
        g, src, to_map, to_loc, viz = self._build(spatial)
        nodes = g._all_nodes()
        # Exactly 4 real nodes: src, to_map, to_loc, viz — no proxy
        assert len(nodes) == 4
        assert src    in nodes
        assert to_map in nodes
        assert to_loc in nodes
        assert viz    in nodes

    def test_node_depths_propagates_through_proxy(self, spatial):
        g, src, to_map, to_loc, viz = self._build(spatial)
        depths = _node_depths(g.nodes)
        # src(0) → to_map(1) → to_loc(2) → [proxy] → viz; viz is also reached
        # directly from to_map, so longest path is 3: src→to_map→to_loc→viz.
        assert depths[src]    == 0
        assert depths[to_map] == 1
        assert depths[to_loc] == 2
        assert depths[viz]    >= 3  # longest path goes through to_loc

    def test_location_pred_not_flagged_as_dangling_sink(self, spatial):
        """MapToLoc has only a proxy in _successors — must not be treated as a
        dangling sink and must not trigger 'not declared as an output'."""
        self._build(spatial)  # would raise if MapToLoc were flagged

    def test_proxy_node_not_flagged_as_undeclared_source(self, spatial):
        """The proxy has no predecessors itself but is invisible to the source
        check in _all_nodes(), so it must not trigger 'not declared as input'."""
        self._build(spatial)  # would raise if proxy were in _all_nodes()

    def test_plot_graph_does_not_raise_with_proxy(self, spatial):
        import matplotlib.pyplot as plt
        g, *_ = self._build(spatial)
        fig = g.plot_graph()
        assert fig is not None
        plt.close("all")

    def test_plot_graph_has_one_patch_per_node(self, spatial):
        """One FancyBboxPatch per real node (4 nodes); legend patches are separate."""
        import matplotlib.pyplot as plt
        g, *_ = self._build(spatial)
        fig = g.plot_graph()
        ax = fig.axes[0]
        assert len(ax.patches) == 4  # exactly src, to_map, to_loc, viz — no proxy box
        plt.close("all")

    def test_summary_does_not_raise_with_proxy(self, spatial, capsys):
        g, *_ = self._build(spatial)
        g.summary()

    def test_summary_proxy_does_not_appear_in_output(self, spatial, capsys):
        g, *_ = self._build(spatial)
        g.summary()
        assert "_SourceProxy" not in capsys.readouterr().out
