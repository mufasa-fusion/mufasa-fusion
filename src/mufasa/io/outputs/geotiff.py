import numpy as np
import rasterio

from mufasa.map import Map
from mufasa.io.outputs.base import OutputNode


class GeoTiffOutput(OutputNode):

    _input_types = [Map]
    _output_type = None
    """Writes the most recently captured Map to a GeoTIFF file.

    On each process() call the current map is copied internally.  On save()
    the last captured map is written to disk as a single-band float64 GeoTIFF.
    If no map was captured (the pipeline never ran) save() is a no-op.
    """

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self._map: Map | None = None

    def process(self) -> None:
        self._map = self._predecessors[0].map.copy()

    def reset(self) -> None:
        self._map = None

    def save(self) -> None:
        if self._map is None:
            return
        data = self._map.data
        if data.ndim == 2:
            write_data = data[np.newaxis, :]
            count, height, width = 1, data.shape[0], data.shape[1]
        else:
            write_data = data
            count, height, width = data.shape

        with rasterio.open(
            self.path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=count,
            dtype=data.dtype,
            crs=self._map.crs,
            transform=self._map.transform,
        ) as dst:
            dst.write(write_data)

    def get_config(self) -> dict:
        return {"path": self.path}
