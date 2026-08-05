from mufasa.location import Location
from mufasa.map import Map
from mufasa.io.outputs.base import OutputNode


class LocationOutput(OutputNode):

    _input_types = [Location]
    _output_type = None
    """Collects Observations or Locations in memory.

    Results are accessible via the .result property after the pipeline runs.
    """

    def __init__(self) -> None:
        super().__init__()
        self._result: list[Location] = []

    @property
    def result(self) -> list[Location]:
        return self._result

    def process(self, loc: Location) -> None:
        self._result.append(self._to_wgs84(loc))

    def reset(self) -> None:
        self._result = []

    def save(self) -> None:
        pass

    def get_config(self) -> dict:
        return {}


class MapOutput(OutputNode):

    _input_types = [Map]
    _output_type = None
    """Collects Map snapshots in memory.

    Snapshots are rate-limited by ``snapshot_interval_s``: a new snapshot is
    only stored if at least that many seconds have elapsed since the last one
    (measured via the predecessor's ``map.timestamp``).  This prevents
    high-frequency pipelines from exhausting memory.

    Copies are taken because map data arrays are mutated in-place upstream.
    Results are accessible via the .result property after the pipeline runs.

    Parameters
    ----------
    snapshot_interval_s : float
        Minimum seconds between stored snapshots.  0 = store every update.
        Default 5.0.
    """

    def __init__(self, snapshot_interval_s: float = 5.0) -> None:
        super().__init__()
        if snapshot_interval_s < 0:
            raise ValueError("snapshot_interval_s must be >= 0")
        self.snapshot_interval_s = snapshot_interval_s
        self._result: list[Map] = []
        self._last_snapshot_time: float | None = None

    @property
    def result(self) -> list[Map]:
        return self._result

    def process(self) -> None:
        pred = self._predecessors[0]
        now = pred.map.timestamp

        if self._last_snapshot_time is not None:
            if now - self._last_snapshot_time < self.snapshot_interval_s:
                return

        self._result.append(pred.map.copy())
        self._last_snapshot_time = now

    def reset(self) -> None:
        self._result = []
        self._last_snapshot_time = None

    def save(self) -> None:
        pass

    def get_config(self) -> dict:
        return {"snapshot_interval_s": self.snapshot_interval_s}
