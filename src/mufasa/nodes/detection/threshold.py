import numpy as np
from rasterio.features import shapes
from scipy.ndimage import binary_dilation, label
from shapely.geometry import shape

from mufasa.location import Location, Observation
from mufasa.map import Map, BayesianMap
from mufasa.node import Node


class Threshold(Node):
    """Detect connected regions in a Map or BayesianMap.

    Output type and accepted input type are resolved at wiring time from the
    predecessor's output type:

    - **BayesianMap predecessor** → accepts ``BayesianMap``, emits
      ``Observation`` (threshold compared against ``map.probabilities``;
      confidence = mean probability across the region).
      Threshold must be in (0, 1).
    - **Plain Map predecessor** → accepts ``Map``, emits ``Location``
      (threshold compared against raw ``map.data``; mean value stored in
      ``properties["mean_value"]``).

    Parameters
    ----------
    threshold : float
        Detection threshold.  For BayesianMap input must be in (0, 1).
    alarm_timeout_s : float
        Minimum seconds between alarm bursts.  0 = alarm on every call
        (no accumulation, default).
    dilation_px : int
        Morphological dilation radius in pixels applied before connected-
        component labelling.  0 = no dilation.
    simplify_m : float
        Shapely simplification tolerance in CRS units (metres for UTM).
        0 = no simplification.
    """

    _input_types = [Map]  # broadest valid default; tightened at wiring time

    def __init__(
        self,
        threshold: float,
        alarm_timeout_s: float = 0.0,
        dilation_px: int = 0,
        simplify_m: float = 0.0,
    ) -> None:
        self._resolved_output_type: type | None = None
        self._resolved_input_types: list = [Map]
        super().__init__()
        if alarm_timeout_s < 0.0:
            raise ValueError("alarm_timeout_s must be >= 0")
        if not isinstance(dilation_px, int) or dilation_px < 0:
            raise ValueError("dilation_px must be int and >= 0")
        if simplify_m < 0.0:
            raise ValueError("simplify_m must be >= 0")
        self.threshold = threshold
        self.alarm_timeout_s = alarm_timeout_s
        self.dilation_px = dilation_px
        self.simplify_m = simplify_m
        self._max_grid: np.ndarray | None = None
        self._last_alarm_time: float | None = None

    @property
    def output_type(self) -> type | None:
        return self._resolved_output_type

    @property
    def input_types(self) -> frozenset:
        return frozenset(self._resolved_input_types)

    def __call__(self, *inputs: "Node") -> "Node":
        if len(inputs) != 1:
            raise TypeError("Threshold accepts exactly one predecessor")
        pred = inputs[0]
        if issubclass(pred.output_type, BayesianMap):
            if not 0.0 < self.threshold < 1.0:
                raise ValueError("threshold must be in (0, 1) for BayesianMap input")
            self._resolved_input_types = [BayesianMap]
            self._resolved_output_type = Observation
        else:
            self._resolved_input_types = [Map]
            self._resolved_output_type = Location
        return super().__call__(*inputs)

    def reset(self) -> None:
        self._max_grid = None
        self._last_alarm_time = None

    def process(self) -> list:
        pred = self._predecessors[0]
        pred_map = pred.map
        timestamp = pred_map.timestamp
        values = self._get_values(pred_map)

        if self._max_grid is None:
            self._max_grid = values.copy()
        else:
            np.maximum(self._max_grid, values, out=self._max_grid)

        if not self._should_alarm(timestamp):
            return []

        outputs = self._detect(self._max_grid, pred_map, timestamp)

        self._max_grid = np.zeros_like(values)
        self._last_alarm_time = timestamp

        for obs in outputs:
            for succ in self._successors:
                succ.process(obs)
        return outputs

    def _get_values(self, m: Map) -> np.ndarray:
        if self._resolved_output_type is Observation:
            return m.probabilities
        return m.data

    def _make_event(self, poly, timestamp, mean_value: float) -> Location:
        if self._resolved_output_type is Observation:
            return Observation(geometry=poly, timestamp=timestamp, confidence=mean_value)
        return Location(geometry=poly, timestamp=timestamp, properties={"mean_value": mean_value})

    def _should_alarm(self, timestamp: float) -> bool:
        if self.alarm_timeout_s == 0.0:
            return True
        if self._last_alarm_time is None:
            return True
        return (timestamp - self._last_alarm_time) >= self.alarm_timeout_s

    def _detect(self, grid: np.ndarray, m: Map, timestamp) -> list:
        mask = (grid >= self.threshold).astype("uint8")
        if not mask.any():
            return []

        if self.dilation_px > 0:
            mask = binary_dilation(mask, iterations=self.dilation_px).astype("uint8")

        labeled, _ = label(mask)
        labeled_int16 = labeled.astype("int16")

        outputs = []
        for geom_dict, comp_id in shapes(
            labeled_int16, mask=mask, transform=m.transform
        ):
            orig_mask = (labeled == int(comp_id)) & (grid >= self.threshold)
            mean_value = float(np.mean(grid[orig_mask]))
            poly = shape(geom_dict)
            if self.simplify_m > 0.0:
                poly = poly.simplify(self.simplify_m)
            outputs.append(self._make_event(poly, timestamp, mean_value))
        return outputs

    def get_config(self) -> dict:
        return {
            "threshold": self.threshold,
            "alarm_timeout_s": self.alarm_timeout_s,
            "dilation_px": self.dilation_px,
            "simplify_m": self.simplify_m,
        }
