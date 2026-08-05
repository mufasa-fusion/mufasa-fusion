"""Tests for Graph.to_config(), from_config(), save(), and load()."""
import json
import pytest
from shapely.geometry import Point, box as shapely_box, mapping

from mufasa import BoundingBox, Observation, Location, Graph
from mufasa.nodes.mapping import POM, StaticMap
from mufasa.nodes.fusion import BayesianFusion, LogicalAnd
from mufasa.nodes.detection import Threshold
from mufasa.nodes.util import ObservationFilter
from mufasa.io.inputs.base import InputNode
from mufasa.io.inputs.geojson import GeoJsonInput


class _MockInput(InputNode):
    _output_type = Observation
    def items(self): return []
    def get_config(self): return {}


# ---------------------------------------------------------------------------
# Shared spatial config
# ---------------------------------------------------------------------------

_SPATIAL = dict(
    crs="EPSG:32633",
    bbox=BoundingBox(14.0, 47.0, 14.1, 47.1),
    resolution=(10.0, 10.0),
)

_CRS_UTM  = "EPSG:32633"
_BBOX_UTM = BoundingBox(500000.0, 5200000.0, 500100.0, 5200100.0)
_RES      = (10.0, 10.0)
_CENTRE_X = 500055.0
_CENTRE_Y = 5200045.0


def _simple_pipeline():
    """_MockInput → POM → Threshold (structure tests only)."""
    src = _MockInput(); src.name = "sensor"
    pom = POM(decay_s=300.0)(src); pom.name = "pom"
    td  = Threshold(0.7)(pom); td.name = "alarm"
    return src, pom, td


def _serializable_pipeline(tmp_path):
    """GeoJsonInput → POM → Threshold (round-trip tests)."""
    events_path = tmp_path / "events.geojson"
    events_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [14.05, 47.05]},
         "properties": {"timestamp": 1.0, "confidence": 0.9}}
    ]}))
    src = GeoJsonInput(path=str(events_path)); src.name = "sensor"
    pom = POM(decay_s=300.0)(src);             pom.name = "pom"
    td  = Threshold(0.7)(pom);       td.name  = "alarm"
    return src, pom, td


from tests.helpers import write_geojson as _write_geojson


# ---------------------------------------------------------------------------
# to_config structure
# ---------------------------------------------------------------------------

class TestToConfig:

    def test_to_config_returns_dict(self):
        src, pom, td = _simple_pipeline()
        m = Graph(inputs=[src], outputs=[td], **_SPATIAL)
        assert isinstance(m.to_config(), dict)

    def test_to_config_has_spatial_section(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert "spatial" in cfg
        assert "crs" in cfg["spatial"]
        assert "bbox" in cfg["spatial"]
        assert "resolution" in cfg["spatial"]

    def test_to_config_spatial_crs_matches(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert cfg["spatial"]["crs"] == _SPATIAL["crs"]

    def test_to_config_spatial_bbox_is_wgs84(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        bbox = cfg["spatial"]["bbox"]
        # WGS84 bbox should be small decimal degrees, NOT UTM metres
        assert all(abs(v) < 180 for v in bbox)
        assert bbox == list(_SPATIAL["bbox"])

    def test_to_config_spatial_resolution(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert cfg["spatial"]["resolution"] == list(_SPATIAL["resolution"])

    def test_to_config_has_inputs_and_outputs(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert "inputs" in cfg
        assert "outputs" in cfg

    def test_to_config_inputs_contains_sensor_name(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert "sensor" in cfg["inputs"]

    def test_to_config_outputs_contains_alarm_name(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert "alarm" in cfg["outputs"]

    def test_to_config_has_nodes_list(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert isinstance(cfg["nodes"], list)

    def test_to_config_nodes_count_matches_pipeline(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        assert len(cfg["nodes"]) == 3  # sensor + pom + td

    def test_to_config_node_has_type_and_name(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        for node in cfg["nodes"]:
            assert "type" in node
            assert "name" in node

    def test_to_config_pom_type_field(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        pom_cfg = next(n for n in cfg["nodes"] if n["name"] == "pom")
        assert pom_cfg["type"] == "POM"

    def test_to_config_pom_params_round_trip(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        pom_cfg = next(n for n in cfg["nodes"] if n["name"] == "pom")
        assert pom_cfg["decay_s"] == pytest.approx(300.0)
        assert pom_cfg["prior"] == pytest.approx(0.5)

    def test_to_config_threshold_decision_params(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        td_cfg = next(n for n in cfg["nodes"] if n["name"] == "alarm")
        assert td_cfg["threshold"] == pytest.approx(0.7)

    def test_to_config_successor_has_inputs_field(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        td_cfg = next(n for n in cfg["nodes"] if n["name"] == "alarm")
        assert td_cfg["inputs"] == ["pom"]

    def test_to_config_source_node_has_no_inputs_field(self):
        src, pom, td = _simple_pipeline()
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        src_cfg = next(n for n in cfg["nodes"] if n["name"] == "sensor")
        assert "inputs" not in src_cfg

    def test_to_config_auto_names_unnamed_nodes(self):
        """Nodes without names get auto-assigned names like 'pom_0'."""
        src = _MockInput()
        pom = POM(decay_s=300.0)(src)
        td  = Threshold(0.7)(pom)
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        names = [n["name"] for n in cfg["nodes"]]
        assert all(isinstance(n, str) and len(n) > 0 for n in names)

    def test_to_config_duplicate_names_raises(self):
        src = _MockInput(); src.name = "same"
        pom = POM(decay_s=300.0)(src); pom.name = "same"
        td  = Threshold(0.7)(pom)
        with pytest.raises(ValueError, match="Duplicate"):
            Graph(inputs=[src], outputs=[td], **_SPATIAL)

    def test_to_config_fan_in_wiring(self):
        """BayesianFusion with two POM predecessors: inputs field lists both."""
        src_a  = _MockInput(); src_a.name = "src_a"
        src_b  = _MockInput(); src_b.name = "src_b"
        pom_a  = POM(decay_s=300.0)(src_a); pom_a.name = "pom_a"
        pom_b  = POM(decay_s=300.0)(src_b); pom_b.name = "pom_b"
        fusion = BayesianFusion()(pom_a, pom_b); fusion.name = "fused"
        td     = Threshold(0.7)(fusion); td.name = "alarm"
        cfg = Graph(inputs=[src_a, src_b], outputs=[td], **_SPATIAL).to_config()
        fused_cfg = next(n for n in cfg["nodes"] if n["name"] == "fused")
        assert set(fused_cfg["inputs"]) == {"pom_a", "pom_b"}


# ---------------------------------------------------------------------------
# from_config round-trip
# ---------------------------------------------------------------------------

class TestFromConfig:

    def _round_trip(self, g: Graph) -> Graph:
        return Graph.from_config(g.to_config())

    def test_round_trip_returns_model_instance(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        assert isinstance(self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL)), Graph)

    def test_round_trip_preserves_crs(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        assert self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL)).crs == _SPATIAL["crs"]

    def test_round_trip_preserves_bbox_wgs84(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        assert self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL)).bbox_wgs84 == _SPATIAL["bbox"]

    def test_round_trip_preserves_resolution(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        assert self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL)).resolution == _SPATIAL["resolution"]

    def test_round_trip_same_node_count(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        m = Graph(inputs=[src], outputs=[td], **_SPATIAL)
        assert len(self._round_trip(m)._all_nodes()) == len(m._all_nodes())

    def test_round_trip_input_node_types_preserved(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        assert type(self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL)).inputs[0]).__name__ == "GeoJsonInput"

    def test_round_trip_output_node_types_preserved(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        assert type(self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL)).outputs[0]).__name__ == "Threshold"  # noqa: E501

    def test_round_trip_node_names_preserved(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        restored = self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL))
        assert restored.inputs[0].name == "sensor"
        assert restored.outputs[0].name == "alarm"

    def test_round_trip_pom_params_preserved(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        restored_pom = next(n for n in self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL))._all_nodes() if type(n).__name__ == "POM")
        assert restored_pom.decay_s == pytest.approx(300.0)
        assert restored_pom.prior  == pytest.approx(0.5)

    def test_round_trip_threshold_decision_params_preserved(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        assert self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL)).outputs[0].threshold == pytest.approx(0.7)

    def test_round_trip_wiring_preserved(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        restored = self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL))
        r_pom = next(n for n in restored._all_nodes() if type(n).__name__ == "POM")
        assert restored.outputs[0] in r_pom._successors

    def test_round_trip_fan_in_wiring_preserved(self, tmp_path):
        _feat = '{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[14.0,47.0]},"properties":{"confidence":0.9,"timestamp":1.0}}]}'
        (tmp_path / "a.geojson").write_text(_feat); src_a = GeoJsonInput(path=str(tmp_path / "a.geojson")); src_a.name = "src_a"
        (tmp_path / "b.geojson").write_text(_feat); src_b = GeoJsonInput(path=str(tmp_path / "b.geojson")); src_b.name = "src_b"
        pom_a  = POM(decay_s=300.0)(src_a); pom_a.name = "pom_a"
        pom_b  = POM(decay_s=300.0)(src_b); pom_b.name = "pom_b"
        fusion = BayesianFusion()(pom_a, pom_b); fusion.name = "fused"
        td     = Threshold(0.7)(fusion); td.name = "alarm"
        restored = self._round_trip(Graph(inputs=[src_a, src_b], outputs=[td], **_SPATIAL))
        r_fused = next(n for n in restored._all_nodes() if type(n).__name__ == "BayesianFusion")
        assert len(r_fused._predecessors) == 2

    def test_round_trip_processes_event_correctly(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        restored = Graph.from_config(Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config())
        r_pom = next(n for n in restored._all_nodes() if type(n).__name__ == "POM")
        r_td  = restored.outputs[0]

        received = []
        class _Sink:
            _successors = []
            def process(self, ev): received.append(ev)
        r_td._successors.append(_Sink())

        b = restored.bbox
        centre = Point((b.min_x + b.max_x) / 2, (b.min_y + b.max_y) / 2)
        r_pom.process(Observation(geometry=centre, timestamp=1.0, confidence=0.9))
        assert len(received) >= 1

    def test_from_config_unknown_type_raises(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        cfg = Graph(inputs=[src], outputs=[td], **_SPATIAL).to_config()
        cfg["nodes"][0]["type"] = "NonExistentNode"
        with pytest.raises(ValueError, match="Unknown node type"):
            Graph.from_config(cfg)

    def test_round_trip_with_static_map(self, tmp_path):
        wgs84_box = shapely_box(14.0, 47.0, 14.1, 47.1)
        prior_path = tmp_path / "priors.geojson"
        features = [{"type": "Feature", "geometry": mapping(wgs84_box), "properties": {"confidence": 0.7}}]
        with open(str(prior_path), "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh)

        events_path = tmp_path / "events3.geojson"
        events_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [14.05, 47.05]},
             "properties": {"timestamp": 1.0, "confidence": 0.9}}
        ]}))
        src    = GeoJsonInput(path=str(events_path)); src.name = "sensor"
        pom    = POM(decay_s=300.0)(src);             pom.name = "pom"
        static = StaticMap(source=str(prior_path));   static.name = "static"
        fusion = BayesianFusion()(pom, static);       fusion.name = "fused"
        td     = Threshold(0.7)(fusion);    td.name = "alarm"
        restored = self._round_trip(Graph(inputs=[src], outputs=[td], **_SPATIAL))
        assert len(restored._all_nodes()) == 5
        assert any(type(n).__name__ == "StaticMap" for n in restored._all_nodes())

    def test_round_trip_observation_filter(self, tmp_path):
        events_path = tmp_path / "events2.geojson"
        events_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [14.05, 47.05]},
             "properties": {"timestamp": 1.0, "confidence": 0.9}}
        ]}))
        src    = GeoJsonInput(path=str(events_path)); src.name = "sensor"
        pom    = POM(decay_s=300.0)(src);             pom.name = "pom"
        fusion = BayesianFusion()(pom);               fusion.name = "fused"
        td     = Threshold(0.7)(fusion);    td.name  = "alarm"
        filt   = ObservationFilter(min_confidence=0.5)(td); filt.name = "filter"
        restored = self._round_trip(Graph(inputs=[src], outputs=[filt], **_SPATIAL))
        filter_node = next(n for n in restored._all_nodes() if type(n).__name__ == "ObservationFilter")
        assert filter_node.min_confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# save() / load() JSON round-trip
# ---------------------------------------------------------------------------

class TestSaveLoad:

    def test_save_creates_file(self, tmp_path):
        src, pom, td = _simple_pipeline()
        m = Graph(inputs=[src], outputs=[td], **_SPATIAL)
        path = tmp_path / "Graph.json"
        m.save(str(path))
        assert path.exists()

    def test_save_file_is_valid_json(self, tmp_path):
        import json
        src, pom, td = _simple_pipeline()
        m = Graph(inputs=[src], outputs=[td], **_SPATIAL)
        path = tmp_path / "Graph.json"
        m.save(str(path))
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "spatial" in data
        assert "nodes" in data

    def test_save_load_round_trip(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        m = Graph(inputs=[src], outputs=[td], **_SPATIAL)
        path = tmp_path / "Graph.json"
        m.save(str(path))
        restored = Graph.load(str(path))
        assert isinstance(restored, Graph)
        assert restored.crs == _SPATIAL["crs"]
        assert restored.bbox_wgs84 == _SPATIAL["bbox"]

    def test_load_pipeline_is_functional(self, tmp_path):
        src, pom, td = _serializable_pipeline(tmp_path)
        m = Graph(inputs=[src], outputs=[td], **_SPATIAL)
        path = tmp_path / "Graph.json"
        m.save(str(path))

        restored = Graph.load(str(path))
        r_pom = next(n for n in restored._all_nodes() if type(n).__name__ == "POM")
        r_td  = restored.outputs[0]

        received = []
        class _Sink:
            _successors = []
            def process(self, ev): received.append(ev)
        r_td._successors.append(_Sink())

        b = restored.bbox
        centre = Point((b.min_x + b.max_x) / 2, (b.min_y + b.max_y) / 2)
        e = Observation(geometry=centre, timestamp=1.0, confidence=0.9)
        r_pom.process(e)
        assert len(received) >= 1

    def test_save_load_with_geojson_input(self, tmp_path):
        from mufasa.io.inputs.geojson import GeoJsonInput
        import json

        events_path = tmp_path / "events.geojson"
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [14.05, 47.05]},
                "properties": {"timestamp": 1.0, "confidence": 0.9}
            }]
        }
        events_path.write_text(json.dumps(geojson))

        src = GeoJsonInput(path=str(events_path)); src.name = "sensor"
        pom = POM(decay_s=300.0)(src); pom.name = "pom"
        td  = Threshold(0.7)(pom); td.name = "alarm"
        m   = Graph(inputs=[src], outputs=[td], **_SPATIAL)

        model_path = tmp_path / "Graph.json"
        m.save(str(model_path))
        restored = Graph.load(str(model_path))

        assert type(restored.inputs[0]).__name__ == "GeoJsonInput"
        assert restored.inputs[0].path == str(events_path)

    def test_json_file_contains_human_readable_structure(self, tmp_path):
        import json
        src, pom, td = _simple_pipeline()
        m = Graph(inputs=[src], outputs=[td], **_SPATIAL)
        path = tmp_path / "Graph.json"
        m.save(str(path))
        data = json.loads(path.read_text())
        assert "spatial" in data
        assert "nodes" in data
        assert any(n["type"] == "POM" for n in data["nodes"])
        assert any(n["type"] == "Threshold" for n in data["nodes"])
