"""Tests for rendering Fusion Graphs as SVG (mufasa.graph_svg)."""

import pytest

from mufasa import BayesianMap, Location, Map, Observation
from mufasa.graph_svg import (
    UNKNOWN_FAMILY,
    FusionGraphCodeError,
    FusionGraphSVG,
    family_of,
    icon_of,
    layout,
    render,
    short_code,
    spec_from_code,
)

EXAMPLE = '''
from mufasa import Graph
from mufasa.io.inputs import GeoJsonInput
from mufasa.io.outputs import GeoJsonOutput
from mufasa.nodes import StaticMap, POM, BayesianFusion, Threshold

track_a = GeoJsonInput("sensor_a.geojson")
track_b = GeoJsonInput("sensor_b.geojson")
static = StaticMap("priors.geojson")

pom_a = POM(decay_s=5)(track_a)
pom_b = POM(decay_s=1)(track_b)
fused = BayesianFusion()(pom_a, pom_b, static)
alarms = Threshold(threshold=0.7)(fused)

out = GeoJsonOutput("alarms.geojson")(alarms)

graph = Graph(inputs=[track_a, track_b], outputs=[out])
graph.run()
'''


class TestShortCode:
    @pytest.mark.parametrize("name, code", [
        ("BayesianFusion", "BF"),
        ("POM", "POM"),
        ("Threshold", "TH"),
        ("GeoJsonInput", "GJI"),
        ("StaticMap", "SM"),
        ("DBSTREAMClusterer", "DC"),
        ("LocationStreamingInput", "LSI"),
    ])
    def test_code(self, name, code):
        assert short_code(name) == code


class TestFamilies:
    def test_subtypes_share_the_family_of_their_root(self):
        assert family_of(Observation) is family_of(Location)
        assert family_of(BayesianMap) is family_of(Map)
        assert family_of(Location) is not family_of(Map)

    def test_unrelated_type_has_unknown_family(self):
        assert family_of(int) is UNKNOWN_FAMILY

    def test_icon_is_most_specific_available(self):
        assert icon_of(BayesianMap) == "map-roll"
        assert icon_of(Map) == "map-fold"
        assert icon_of(Observation) == "observation-marker"


class TestSpecFromCode:
    def test_example_nodes_and_edges(self):
        spec = spec_from_code(EXAMPLE)
        assert list(spec.nodes) == ["track_a", "track_b", "static", "pom_a", "pom_b", "fused", "alarms", "out"]
        assert len(spec.edges) == 7
        assert ("static", "fused") in spec.edges

    def test_roles_follow_declared_types(self):
        spec = spec_from_code(EXAMPLE)
        assert spec.nodes["track_a"].is_input
        assert spec.nodes["static"].is_input
        assert spec.nodes["out"].is_output
        assert not spec.nodes["fused"].is_input and not spec.nodes["fused"].is_output

    def test_types_resolved_later_use_the_broadest_declared_types(self):
        spec = spec_from_code(EXAMPLE)
        assert spec.nodes["track_a"].output_type is Location  # Location or Observation, depending on the file
        assert spec.nodes["alarms"].input_types == [Map]  # Threshold resolves its types at wiring time
        assert spec.nodes["alarms"].output_type is Location

    def test_input_must_be_a_defined_node(self):
        code = "from mufasa.nodes import POM\npom = POM(decay_s=5)(missing)"
        with pytest.raises(FusionGraphCodeError, match="line 2"):
            spec_from_code(code)

    def test_unknown_class_raises(self):
        with pytest.raises(FusionGraphCodeError, match="line 1: unknown name 'Missing'"):
            spec_from_code("x = Missing()")

    def test_functions_defined_in_the_example_are_not_nodes(self):
        code = "from mufasa.nodes import StaticMap\ndef prior():\n    return 'p.geojson'\ns = StaticMap(prior())"
        assert list(spec_from_code(code).nodes) == ["s"]

    def test_code_without_nodes_raises(self):
        with pytest.raises(FusionGraphCodeError, match="no nodes"):
            spec_from_code("x = 1")

    def test_invalid_python_raises(self):
        with pytest.raises(FusionGraphCodeError, match="invalid Python"):
            spec_from_code("pom = (")


class TestLayout:
    def test_edges_point_downwards(self):
        spec = spec_from_code(EXAMPLE)
        positions = layout(spec).nodes
        assert all(positions[a][1] < positions[b][1] for a, b in spec.edges)

    def test_source_sits_one_layer_above_its_successor(self):
        positions = layout(spec_from_code(EXAMPLE)).nodes
        assert positions["static"][1] == positions["pom_a"][1]

    def test_single_successor_is_centered_below_its_inputs(self):
        positions = layout(spec_from_code(EXAMPLE)).nodes
        assert positions["track_a"][0] == positions["pom_a"][0]

    def test_edge_skipping_a_layer_bends_around_the_node_in_between(self):
        code = ("from mufasa.nodes import StaticMap, BayesianFusion\n"
                "a = StaticMap('p.geojson')\nb = BayesianFusion()(a)\nc = BayesianFusion()(b, a)")
        result = layout(spec_from_code(code))
        [(bend_x, bend_y)] = result.bends["a", "c"]  # One bend, in the layer of b
        assert bend_y == result.nodes["b"][1]
        assert bend_x != result.nodes["b"][0]
        assert result.bends["a", "b"] == []


class TestRender:
    def test_svg_is_self_contained(self):
        svg = render(spec_from_code(EXAMPLE))
        assert svg.startswith("<svg") and svg.endswith("</svg>")
        assert "<style>" in svg and "<script>" in svg and "<symbol" in svg

    def test_boundary_and_processing_nodes(self):
        svg = render(spec_from_code(EXAMPLE))
        assert svg.count('class="mf-node mf-io"') == 4  # track_a, track_b, static, out
        assert svg.count('class="mf-node mf-proc"') == 4

    def test_ids_are_unique_per_graph(self):
        spec = spec_from_code(EXAMPLE)
        assert 'id="first-location-marker"' in render(spec, prefix="first")
        assert render(spec) != render(spec)  # Automatic prefixes differ

    def test_save_writes_svg(self, tmp_path):
        path = tmp_path / "graph.svg"
        FusionGraphSVG(render(spec_from_code(EXAMPLE))).save(path)
        assert path.read_text(encoding="utf-8").startswith("<svg")
