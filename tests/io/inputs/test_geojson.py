from pathlib import Path

from mufasa import Observation, Location
from mufasa.io.inputs.base import InputNode
from mufasa.io.inputs.geojson import GeoJsonInput

TEST_DATA = Path(__file__).parent.parent.parent / "test_data" / "inputs"


class TestGeoJsonInput:
    def test_is_input_node(self):
        assert issubclass(GeoJsonInput, InputNode)

    def test_load_events_returns_location_objects(self):
        items = GeoJsonInput(TEST_DATA / "events.geojson").items()
        assert all(type(i) is Location for i in items)

    def test_load_events_sorted_by_timestamp(self):
        items = GeoJsonInput(TEST_DATA / "events.geojson").items()
        timestamps = [e.timestamp for e in items]
        assert timestamps == sorted(timestamps)

    def test_load_events_count(self):
        assert len(GeoJsonInput(TEST_DATA / "events.geojson").items()) == 3

    def test_load_events_timestamp_values(self):
        items = GeoJsonInput(TEST_DATA / "events.geojson").items()
        assert [e.timestamp for e in items] == [100.0, 200.0, 300.0]

    def test_load_events_properties_preserved(self):
        items = GeoJsonInput(TEST_DATA / "events.geojson").items()
        assert [e.properties["label"] for e in items] == ["a", "b", "c"]

    def test_load_locations_returns_location_objects(self):
        items = GeoJsonInput(TEST_DATA / "locations.geojson").items()
        assert all(type(i) is Location for i in items)

    def test_load_locations_count(self):
        assert len(GeoJsonInput(TEST_DATA / "locations.geojson").items()) == 2

    def test_load_locations_properties_preserved(self):
        items = GeoJsonInput(TEST_DATA / "locations.geojson").items()
        assert {i.properties["name"] for i in items} == {"alpha", "beta"}

    def test_output_type_is_observation_when_confidence_present(self):
        assert GeoJsonInput(TEST_DATA / "events_with_confidence.geojson").output_type is Observation

    def test_output_type_is_location_when_no_confidence(self):
        assert GeoJsonInput(TEST_DATA / "locations.geojson").output_type is Location

    def test_output_type_is_location_when_timestamp_but_no_confidence(self):
        assert GeoJsonInput(TEST_DATA / "events.geojson").output_type is Location

    def test_confidence_column_mapped_to_event_confidence(self):
        items = GeoJsonInput(TEST_DATA / "events_with_confidence.geojson").items()
        assert items[0].confidence == 0.9
        assert items[1].confidence == 0.3

    def test_confidence_not_duplicated_in_properties(self):
        items = GeoJsonInput(TEST_DATA / "events_with_confidence.geojson").items()
        assert "confidence" not in items[0].properties

    def test_locations_with_timestamps_carry_timestamp(self):
        items = GeoJsonInput(TEST_DATA / "events.geojson").items()
        assert all(isinstance(i, Location) and i.timestamp > 0 for i in items)
