import numpy as np

from mufasa.map import BayesianMap
from mufasa.node import Node


class MapFusion(Node):
    """Base for fusion nodes that combine BayesianMaps element-wise.

    The output BayesianMap is allocated once on the first process() call and
    reused thereafter; data is updated in-place via numpy's out= parameter.

    Subclasses implement _combine(stacked, out=None) to define the reduction.
    """

    _input_types = [BayesianMap]
    _output_type = BayesianMap

    def __init__(self) -> None:
        super().__init__()
        self._current_map: BayesianMap | None = None

    def configure(self, crs, bbox, resolution) -> None:
        self._current_map = BayesianMap.from_bounds(bbox, resolution, crs)

    @property
    def map(self) -> BayesianMap:
        if self._current_map is None:
            raise RuntimeError("configure() must be called before accessing map")
        return self._current_map

    def reset(self) -> None:
        if self._current_map is not None:
            self._current_map.data[:] = 0.0
            self._current_map.timestamp = 0.0

    def process(self) -> BayesianMap:
        stacked = np.stack([pred.map.data for pred in self._predecessors])
        self._current_map.timestamp = max(p.map.timestamp for p in self._predecessors)
        self._combine(stacked, out=self._current_map.data)
        self._trigger_successors()
        return self._current_map

    def _combine(self, stacked: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def get_config(self) -> dict:
        return {}


class BayesianFusion(MapFusion):
    """Fuse two or more BayesianMaps by summing their log-odds.

    Assumes conditional independence between sources. Inputs and output are
    all in log-odds space (BayesianMap.data); no logit/expit conversions needed.
    """

    def _combine(self, stacked: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
        return np.nansum(stacked, axis=0, out=out)


class LogicalAnd(MapFusion):
    """Logical AND in log-odds space: element-wise minimum across inputs.

    Conservative fusion — a cell is occupied only if all sources agree.
    """

    def _combine(self, stacked: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
        return np.nanmin(stacked, axis=0, out=out)


class LogicalOr(MapFusion):
    """Logical OR in log-odds space: element-wise maximum across inputs.

    Permissive fusion — a cell is occupied if any source indicates it.
    """

    def _combine(self, stacked: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
        return np.nanmax(stacked, axis=0, out=out)
