import json
import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from scipy.special import logit
from shapely.geometry import shape
from shapely.ops import transform

from mufasa.map import Map, BayesianMap
from mufasa.node import Node

_PMIN = 1e-5
_PMAX = 1.0 - 1e-5
_SOURCE_CRS = "EPSG:4326"  # GeoJSON spec mandates WGS84


class StaticMap(Node):
    """Source node: load a BayesianMap from a GeoJSON file at configure() time.

    Each feature defines a spatial region and its prior probability via a
    'confidence' property (0–1).  Regions not covered by any feature remain
    NaN so BayesianFusion (nansum) ignores them, contributing nothing to the
    fused output for those pixels.

    For overlapping features the lower confidence wins (most conservative
    prior).

    The node is a source — it has no predecessors — so it must be declared
    in Graph(inputs=[..., static_map]).  Its map is fully populated after
    configure() and never changes; process() is a no-op.
    """

    _input_types = []
    _output_type = BayesianMap

    def __init__(self, source: str, default_prior: float = 0.5) -> None:
        super().__init__()
        if not 0.0 < default_prior < 1.0:
            raise ValueError("default_prior must be in (0, 1)")
        self.source = source
        self.default_prior = default_prior
        self._map: BayesianMap | None = None

    @property
    def map(self) -> BayesianMap:
        if self._map is None:
            raise RuntimeError("configure() must be called before accessing map")
        return self._map

    def configure(self, crs, bbox, resolution) -> None:
        with open(self.source, encoding="utf-8") as fh:
            data = json.load(fh)

        if data.get("type") == "FeatureCollection":
            features = data.get("features") or []
        elif data.get("type") == "Feature":
            features = [data]
        else:
            features = []

        template = Map.from_bounds(bbox, resolution, crs)

        reproject = None
        crs_str = template.crs.to_string() if hasattr(template.crs, "to_string") else str(crs)
        if crs_str != _SOURCE_CRS:
            t = Transformer.from_crs(_SOURCE_CRS, crs_str, always_xy=True)
            reproject = lambda geom: transform(t.transform, geom)  # noqa: E731

        arr = np.full(template.data.shape, np.nan, dtype=np.float64)

        for feature in features:
            if not feature.get("geometry"):
                continue
            geom = shape(feature["geometry"])
            if geom.is_empty:
                continue

            props = feature.get("properties") or {}
            conf = float(props["confidence"]) if "confidence" in props else self.default_prior
            lo = logit(np.clip(conf, _PMIN, _PMAX))

            if reproject is not None:
                geom = reproject(geom)

            mask = rasterize(
                [(geom, 1)],
                out_shape=arr.shape,
                transform=template.transform,
                fill=0,
                dtype="uint8",
            ).astype(bool)

            arr[mask] = np.where(
                np.isnan(arr[mask]),
                lo,
                np.minimum(arr[mask], lo),
            )

        self._map = BayesianMap(arr, template.transform, template.crs)

    def process(self) -> None:
        """Static maps carry no temporal events — intentional no-op."""

    def get_config(self) -> dict:
        return {"source": self.source, "default_prior": self.default_prior}
