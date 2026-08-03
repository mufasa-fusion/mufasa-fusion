from typing import NamedTuple

import numpy as np
from rasterio.crs import CRS
from scipy.special import expit as _expit
from rasterio.transform import Affine, array_bounds
from rasterio.transform import from_bounds as _transform_from_bounds


class BoundingBox(NamedTuple):
    min_x: float
    min_y: float
    max_x: float
    max_y: float


class Map:
    def __init__(
        self,
        data: np.ndarray,
        transform: Affine,
        crs: "CRS | None" = None,
        *,
        timestamp: float = 0.0,
    ) -> None:
        self.data = data
        self.transform = transform
        self.crs = crs
        self.timestamp = timestamp

    @classmethod
    def from_bounds(
        cls,
        bounds: BoundingBox,
        resolution: tuple[float, float],
        crs: "str | CRS | None" = None,
    ) -> "Map":
        width = round((bounds.max_x - bounds.min_x) / resolution[0])
        height = round((bounds.max_y - bounds.min_y) / resolution[1])
        transform = _transform_from_bounds(
            bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y,
            width, height,
        )
        if isinstance(crs, str):
            crs = CRS.from_string(crs)
        return cls(np.zeros((height, width), dtype=np.float64), transform, crs)

    @property
    def bbox(self) -> BoundingBox:
        height, width = self.data.shape[:2]
        west, south, east, north = array_bounds(height, width, self.transform)
        return BoundingBox(west, south, east, north)

    def copy(self) -> "Map":
        return type(self)(self.data.copy(), self.transform, self.crs, timestamp=self.timestamp)

    def reproject(
        self,
        crs: "str | CRS",
        bbox: BoundingBox,
        resolution: tuple[float, float],
    ) -> "Map":
        from rasterio.warp import reproject as _warp, Resampling
        if self.crs is None:
            raise ValueError(
                "Cannot reproject a Map with no CRS. "
                "Assign a CRS when constructing the Map, or use a pipeline without a CRS."
            )
        dst_crs = CRS.from_string(crs) if isinstance(crs, str) else crs
        if dst_crs is None:
            raise ValueError("Cannot reproject to a destination with no CRS.")
        dst = type(self).from_bounds(bbox, resolution, dst_crs)
        _warp(
            source=self.data,
            destination=dst.data,
            src_transform=self.transform,
            src_crs=self.crs,
            dst_transform=dst.transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
        )
        dst.timestamp = self.timestamp
        return dst


class BayesianMap(Map):
    """Map subtype produced by Bayesian nodes (POM, StaticMap).

    ``data`` stores values in log-odds space. Use the ``probabilities``
    property to obtain the equivalent values in [0, 1]. Fusion nodes
    (BayesianFusion, LogicalAnd/Or) operate directly on ``data`` to avoid
    repeated logit/expit round-trips.
    """

    @property
    def probabilities(self) -> np.ndarray:
        """Return a copy of the map data converted to probabilities in [0, 1]."""
        return _expit(self.data)
