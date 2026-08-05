"""Shared test utilities."""
import json
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform
from mufasa import BoundingBox

CRS      = "EPSG:32633"
BBOX     = BoundingBox(500000.0, 5200000.0, 500100.0, 5200100.0)
RES      = (10.0, 10.0)
CENTRE_X = 500055.0
CENTRE_Y = 5200045.0

_to_wgs84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def write_geojson(path, geometries, confidences=None):
    """Write UTM (EPSG:32633) geometries to a WGS84 GeoJSON file."""
    features = []
    for i, geom in enumerate(geometries):
        wgs84 = transform(_to_wgs84.transform, geom)
        props = {"confidence": float(confidences[i])} if confidences is not None else {}
        features.append({"type": "Feature", "geometry": mapping(wgs84), "properties": props})
    with open(str(path), "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
