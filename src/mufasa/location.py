from dataclasses import dataclass, field

import numpy as np
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


@dataclass(eq=False)
class UncertainObservation(Observation):
    """Observation with a Gaussian position uncertainty.
    
    ``covariance`` is a symmetric, positive-definite 2×2 matrix in pipeline
    CRS units squared (m² for UTM), ordered ``[x, y]`` like the geometry
    coordinates. Input and output nodes reproject only the geometry, so give
    the covariance in metres even when supplying WGS84 coordinates; for a UTM
    pipeline this is the east/north covariance a sensor typically reports.
    """

    covariance: np.ndarray = field(kw_only=True)

    def __post_init__(self) -> None:
        cov = np.array(self.covariance, dtype=float)
        if cov.shape != (2, 2):
            raise ValueError(f"covariance must have shape (2, 2), got {cov.shape}")
        if not np.all(np.isfinite(cov)):
            raise ValueError("covariance must contain only finite values")
        if not np.allclose(cov, cov.T):
            raise ValueError("covariance must be symmetric")
        try:
            np.linalg.cholesky(cov)
        except np.linalg.LinAlgError:
            raise ValueError("covariance must be positive definite") from None
        self.covariance = cov

    def __eq__(self, other) -> bool:
        # The generated dataclass __eq__ would compare the ndarray with ``==``,
        # which is ambiguous for arrays and raises instead of returning a bool.
        if other.__class__ is not self.__class__:
            return NotImplemented
        return super().__eq__(other) and np.array_equal(self.covariance, other.covariance)
