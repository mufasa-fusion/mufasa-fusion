import numpy as np
import rasterio

from mufasa.map import Map
from mufasa.io.inputs.base import InputNode


class GeoTiffInput(InputNode):
    """Loads a single-band GeoTIFF file as a Map.

    The raster is returned in its native CRS. Reprojection and resampling to
    the pipeline's CRS, bounding box, and resolution is handled automatically
    by the InputNode base class.
    """

    _input_types = []
    _output_type = Map

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    def items(self) -> list[Map]:
        with rasterio.open(self.path) as src:
            data = src.read(1).astype(np.float64)
            if src.nodata is not None:
                data[data == src.nodata] = 0.0
            return [Map(data, src.transform, src.crs)]

    def get_config(self) -> dict:
        return {"path": self.path}
