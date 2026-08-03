import dataclasses

from pyproj import Transformer
from shapely.ops import transform as _shapely_transform

from mufasa.node import Node, _NOT_SET


class OutputNode(Node):
    """Base for all pipeline output nodes. Has no output type."""

    _input_types = _NOT_SET
    _output_type = None

    def __init__(self) -> None:
        super().__init__()
        self._wgs84_transformer = None

    def configure(self, crs, bbox, resolution) -> None:
        self._wgs84_transformer = None
        if self._accepts_locations() and crs is not None:
            crs_str = crs if isinstance(crs, str) else crs.to_string()
            if crs_str != "EPSG:4326":
                t = Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
                self._wgs84_transformer = lambda geom, _t=t: _shapely_transform(_t.transform, geom)

    def _accepts_locations(self) -> bool:
        from mufasa.location import Location
        types = type(self)._input_types
        return types is not _NOT_SET and any(issubclass(t, Location) for t in types)

    def _to_wgs84(self, loc):
        if self._wgs84_transformer is None:
            return loc
        return dataclasses.replace(loc, geometry=self._wgs84_transformer(loc.geometry))

    def save(self) -> None:
        """Persist any buffered output to its destination.

        No-op by default.  Subclasses that buffer results (GeoJsonOutput,
        GeoTiffOutput, etc.) override this to flush to disk.  Called by
        Graph.run() after all inputs have been processed.
        """
