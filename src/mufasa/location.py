from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiLineString, MultiPoint, Point
from shapely.geometry.base import BaseGeometry


@dataclass
class Location:
    geometry:   BaseGeometry
    timestamp:  float = 0.0
    properties: dict = field(default_factory=dict)

    def _expand_geometry(self) -> BaseGeometry | None:
        """Return geometry expanded by radius/width properties where applicable.

        Point / MultiPoint: buffered by the ``radius`` property (CRS units) if present.
        LineString / MultiLineString: buffered by ``width / 2`` if a ``width`` property
        is present, producing a corridor polygon.
        All other types, or geometries without the matching property, are returned
        unchanged.  ``None`` geometry is returned as-is.
        """
        geom = self.geometry
        if geom is None:
            return None
        if isinstance(geom, (Point, MultiPoint)):
            radius = self.properties.get("radius")
            if radius is not None:
                return geom.buffer(float(radius))
        elif isinstance(geom, (LineString, MultiLineString)):
            width = self.properties.get("width")
            if width is not None:
                return geom.buffer(float(width) / 2.0)
        return geom

    @property
    def effective_geometry(self) -> BaseGeometry | None:
        """Geometry expanded by radius/width properties, or raw geometry if not applicable.

        Use this instead of ``geometry`` whenever spatial footprint matters —
        e.g. rasterization, intersection checks — so that sensor uncertainty
        expressed through Observation properties is automatically respected.
        """
        return self._expand_geometry()


@dataclass
class Observation(Location):
    confidence: float = 0.5
