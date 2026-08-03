import json

from shapely.geometry import shape

from mufasa.location import Observation, Location
from mufasa.io.inputs.base import InputNode

_TIMESTAMP_COLS = ("timestamp", "time", "datetime")
_CONFIDENCE_COL = "confidence"


def _read_features(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("type") == "FeatureCollection":
        return data.get("features") or []
    if data.get("type") == "Feature":
        return [data]
    return []


def _has_confidence(path) -> bool:
    features = _read_features(path)
    if not features:
        return False
    props = features[0].get("properties") or {}
    return _CONFIDENCE_COL in props


class GeoJsonInput(InputNode):
    """Loads Observations or Locations from a GeoJSON file.

    output_type is Observation if a 'confidence' column is present, otherwise
    Location. Timestamps are mapped to the timestamp field on either type.
    Determined at construction time by reading the first feature of the file.

    Geometries are in WGS84 (GeoJSON spec) and are reprojected to the pipeline
    CRS automatically by the InputNode base class.

    Override decode() in a subclass to produce a richer type for potential nodes
    that have stricter requirements. Also set _output_type on the subclass so
    the DAG wiring validation sees the correct type.
    """

    _input_types = []

    def __init__(self, path: str) -> None:
        self._output_type: type = Observation if _has_confidence(path) else Location
        super().__init__()
        self.path = path

    @property
    def output_type(self) -> type:
        return self._output_type

    def decode(self, feature: dict) -> Location:
        """Convert a single GeoJSON feature dict to a Location or Observation.

        Returns geometry in WGS84; reprojection to pipeline CRS is handled
        automatically by the InputNode base class before the item reaches
        any processing node. Override in a subclass to produce a richer type.
        """
        props = dict(feature.get("properties") or {})
        geom = shape(feature["geometry"])

        ts_key = next((k for k in _TIMESTAMP_COLS if props.get(k) is not None), None)
        conf_val = props.get(_CONFIDENCE_COL)
        timestamp = float(props[ts_key]) if ts_key is not None else 0.0

        skip = {_CONFIDENCE_COL, ts_key} - {None}
        free_props = {k: v for k, v in props.items() if k not in skip}

        if conf_val is not None:
            return Observation(
                geometry=geom,
                timestamp=timestamp,
                confidence=float(conf_val),
                properties=free_props,
            )
        return Location(geometry=geom, timestamp=timestamp, properties=free_props)

    def items(self) -> list[Location]:
        result = [self.decode(f) for f in _read_features(self.path)]
        return sorted(result, key=lambda e: e.timestamp)

    def get_config(self) -> dict:
        return {"path": self.path}
