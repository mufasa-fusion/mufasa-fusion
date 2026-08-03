import dataclasses
from abc import abstractmethod

from pyproj import Transformer
from shapely.ops import transform as _shapely_transform

from mufasa.map import Map
from mufasa.node import Node, _NOT_SET


class InputNode(Node):
    """Base for all pipeline input nodes. Has no predecessor inputs."""

    _input_types = []
    _output_type = _NOT_SET

    def __init__(self) -> None:
        super().__init__()
        self._pipeline_crs = None
        self._pipeline_bbox = None
        self._pipeline_resolution = None
        if issubclass(self.output_type, Map):
            self._dispatch = self._dispatch_map
            self.map = None
        else:
            self._loc_transformer = None
            self._dispatch = self._dispatch_location

    def configure(self, crs, bbox, resolution) -> None:
        self._pipeline_crs = crs
        self._pipeline_bbox = bbox
        self._pipeline_resolution = resolution
        if not issubclass(self.output_type, Map):
            if crs is not None:
                crs_str = crs if isinstance(crs, str) else crs.to_string()
                if crs_str != "EPSG:4326":
                    t = Transformer.from_crs("EPSG:4326", crs_str, always_xy=True)
                    self._loc_transformer = lambda geom, _t=t: _shapely_transform(_t.transform, geom)

    def _dispatch_map(self, item: Map) -> None:
        if self._pipeline_crs is not None and self._pipeline_bbox is not None and self._pipeline_resolution is not None:
            expected = Map.from_bounds(self._pipeline_bbox, self._pipeline_resolution, self._pipeline_crs)
            if item.crs != expected.crs or item.transform != expected.transform or item.data.shape != expected.data.shape:
                item = item.reproject(self._pipeline_crs, self._pipeline_bbox, self._pipeline_resolution)
        self.map = item
        for succ in self._successors:
            succ.process()

    def _dispatch_location(self, item) -> None:
        if self._loc_transformer is not None:
            item = dataclasses.replace(item, geometry=self._loc_transformer(item.geometry))
        for succ in self._successors:
            succ.process(item)
            
    @abstractmethod
    def items(self):
        """Return items from this input in temporal order.

        File-based nodes return a sorted list. Streaming nodes return a
        blocking generator that yields as items arrive via ingest().
        """

    def run(self) -> None:
        for item in self.items():
            self._dispatch(item)

    def process(self, *args, **kwargs) -> None:
        """Input nodes do not receive process() calls from the framework."""
