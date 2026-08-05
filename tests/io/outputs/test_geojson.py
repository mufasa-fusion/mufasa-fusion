import json

import pytest
from shapely.geometry import Point

from mufasa.location import Observation, Location
from mufasa.io.outputs.base import OutputNode
from mufasa.io.outputs.geojson import GeoJsonOutput


class TestGeoJsonOutput:
    def test_is_file_output_mixin(self):
        assert issubclass(GeoJsonOutput, OutputNode)

    def test_stores_path(self):
        assert GeoJsonOutput("out.geojson").path == "out.geojson"

    def test_save_empty_writes_file(self, tmp_path):
        out = GeoJsonOutput(str(tmp_path / "out.geojson"))
        out.save()  # empty — should not raise

    def test_save_writes_feature_collection(self, tmp_path):
        out = GeoJsonOutput(str(tmp_path / "out.geojson"))
        out.process(Location(geometry=Point(0, 0)))
        out.save()
        data = json.loads((tmp_path / "out.geojson").read_text())
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

    def test_observation_confidence_and_timestamp_written(self, tmp_path):
        out = GeoJsonOutput(str(tmp_path / "out.geojson"))
        out.process(Observation(geometry=Point(0, 0), timestamp=42.0, confidence=0.8))
        out.save()
        props = json.loads((tmp_path / "out.geojson").read_text())["features"][0]["properties"]
        assert props["confidence"] == pytest.approx(0.8)
        assert props["timestamp"] == pytest.approx(42.0)

    def test_custom_properties_preserved(self, tmp_path):
        out = GeoJsonOutput(str(tmp_path / "out.geojson"))
        obs = Observation(geometry=Point(0, 0), timestamp=1.0, confidence=0.5,
                          properties={"source": "radar", "label": "vessel"})
        out.process(obs)
        out.save()
        props = json.loads((tmp_path / "out.geojson").read_text())["features"][0]["properties"]
        assert props["source"] == "radar"
        assert props["label"] == "vessel"
