import json

from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform

from mufasa.location import Observation, Location
from mufasa.io.outputs.base import OutputNode

_TARGET_CRS = "EPSG:4326"  # GeoJSON spec mandates WGS84


class GeoJsonOutput(OutputNode):
    """Writes collected Observations or Locations to a GeoJSON file (WGS84).

    All properties from Location.properties are included.  For Observation
    objects, confidence and timestamp are additionally written as top-level
    feature properties.

    Override encode() in a subclass to serialise richer types (e.g.
    UncertainObservation) to custom GeoJSON properties.
    """

    _input_types = [Location]
    _output_type = None

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self._outputs: list[Location] = []
        self._crs: str | None = None
        self._reproject = None

    def configure(self, crs, bbox, resolution) -> None:
        self._crs = crs
        if crs is not None and crs != _TARGET_CRS:
            t = Transformer.from_crs(crs, _TARGET_CRS, always_xy=True)
            self._reproject = lambda geom: transform(t.transform, geom)  # noqa: E731

    def encode(self, loc: Location) -> dict:
        """Convert a Location or Observation to a GeoJSON feature dict.

        Geometry is reprojected to WGS84 (accessible via self._reproject).
        Override in a subclass to serialise additional typed fields.
        """
        geom = loc.geometry
        if self._reproject is not None:
            geom = self._reproject(geom)

        props = dict(loc.properties)
        if isinstance(loc, Observation):
            props["confidence"] = loc.confidence
            props["timestamp"] = loc.timestamp

        return {
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": props,
        }

    def process(self, loc: Location) -> None:
        self._outputs.append(loc)

    def reset(self) -> None:
        self._outputs = []

    def save(self) -> None:
        features = [self.encode(loc) for loc in self._outputs]
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh, ensure_ascii=False)

    def get_config(self) -> dict:
        return {"path": self.path}
