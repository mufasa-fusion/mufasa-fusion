from abc import abstractmethod

import numpy as np
from rasterio.features import rasterize
from shapely.geometry import Point, MultiPoint

from mufasa.location import Observation
from mufasa.map import Map
from mufasa.node import Node


class HeatMap(Node):
    """Base class for Observation-ingesting map nodes with temporal decay.

    Subclasses declare their output map type via the ``_map_class`` class
    variable (default ``Map``). POM sets it to ``BayesianMap``.

    A single Map object is allocated in ``configure()`` and reused across all
    ``process()`` calls.  ``self._data`` is an alias for ``self._map.data``
    so subclass hooks (``_decay``, ``_model_update``) operate directly on the
    live array with no copies.

    Subclasses must implement:
        _decay(delta_t_s):               apply time decay to internal state
        _model_update(mask, confidence): update cells under the Observation footprint
        get_config() -> dict:            constructor arguments for serialization
    """

    _map_class: type = Map
    _input_types = [Observation]
    _output_type = Map

    def __init__(self, decay_s: float) -> None:
        super().__init__()
        if decay_s <= 0:
            raise ValueError("decay_s must be > 0")
        self.decay_s = decay_s
        self._map: Map | None = None
        self._data: np.ndarray | None = None   # alias for self._map.data
        self._transform = None
        self._crs = None

    # ------------------------------------------------------------------
    # Spatial configuration
    # ------------------------------------------------------------------

    def configure(self, crs, bbox, resolution) -> None:
        template = Map.from_bounds(bbox, resolution, crs)
        init_data = self._init_data(template.data.shape)
        self._map = self._map_class(init_data, template.transform, template.crs)
        self._data = self._map.data
        self._transform = self._map.transform
        self._crs = self._map.crs

    def _init_data(self, shape: tuple) -> np.ndarray:
        """Return the initial data array. Override for non-zero initialisation."""
        return np.zeros(shape, dtype=np.float64)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def map(self) -> Map:
        """Current map — the same object is returned on every call."""
        if self._map is None:
            raise RuntimeError("configure() must be called before accessing map")
        return self._map

    def process(self, obs: Observation):
        if self._data is None:
            raise RuntimeError("configure() must be called before process()")
        prev_ts = self._map.timestamp
        delta_t = obs.timestamp - prev_ts
        if delta_t > 0:
            self._decay(delta_t)
        mask = self._get_mask(obs)
        self._model_update(mask, obs.confidence)
        self._map.timestamp = max(obs.timestamp, prev_ts)
        self._trigger_successors()
        return self._map

    def reset(self) -> None:
        if self._map is not None:
            self._data[:] = self._init_data(self._data.shape)
            self._map.timestamp = 0.0

    def flush(self) -> None:
        """No buffered state to emit at end of stream."""

    # ------------------------------------------------------------------
    # Mask generation
    # ------------------------------------------------------------------

    def _get_mask(self, obs: Observation) -> np.ndarray:
        """Rasterize Observation geometry into a boolean pixel mask.

        Uses ``obs.effective_geometry`` so that Point radius and LineString
        width properties are automatically applied before rasterization.
        """
        geom = obs.effective_geometry
        if geom is None:
            return np.zeros(self._data.shape, dtype=bool)
        return rasterize(
            [(geom, 1)],
            out_shape=self._data.shape,
            transform=self._transform,
            fill=0,
            dtype="uint8",
            all_touched=isinstance(geom, (Point, MultiPoint)),
        ).astype(bool)

    # ------------------------------------------------------------------
    # Abstract hooks
    # ------------------------------------------------------------------

    @abstractmethod
    def _decay(self, delta_t_s: float) -> None: ...

    @abstractmethod
    def _model_update(self, mask: np.ndarray, confidence: float) -> None: ...

    @abstractmethod
    def get_config(self) -> dict: ...
