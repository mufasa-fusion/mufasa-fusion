import re

from mufasa.location import Observation
from mufasa.node import Node


class ObservationFilter(Node):
    """Pass-through node that drops Observations not matching the specified criteria.

    All criteria are AND-combined: an Observation must satisfy every specified
    criterion to be forwarded to successors.

    Parameters
    ----------
    min_confidence : float
        Minimum confidence (inclusive). Observations below this value are dropped.
        Default 0.0 passes everything.
    start_time : float | None
        Only pass observations with timestamp >= start_time.
    end_time : float | None
        Only pass observations with timestamp < end_time.
    properties : dict[str, str] | None
        Map of property key -> regex pattern.  An Observation passes only if,
        for every key, ``str(obs.properties.get(key, ""))`` fully matches the
        corresponding pattern.  None (default) applies no property filter.
    """

    _input_types = [Observation]
    _output_type = Observation

    def __init__(
        self,
        min_confidence: float = 0.0,
        start_time: float | None = None,
        end_time: float | None = None,
        properties: dict | None = None,
    ) -> None:
        super().__init__()
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        self.min_confidence = min_confidence
        self.start_time = start_time
        self.end_time = end_time
        self._patterns: dict[str, re.Pattern] = {
            k: re.compile(v) for k, v in (properties or {}).items()
        }

    def process(self, obs: Observation) -> None:
        if self._passes(obs):
            for succ in self._successors:
                succ.process(obs)

    def _passes(self, obs: Observation) -> bool:
        if not isinstance(obs, Observation):
            return False
        if obs.confidence < self.min_confidence:
            return False
        if self.start_time is not None and obs.timestamp < self.start_time:
            return False
        if self.end_time is not None and obs.timestamp >= self.end_time:
            return False
        for key, pattern in self._patterns.items():
            value = str(obs.properties.get(key, ""))
            if not pattern.fullmatch(value):
                return False
        return True

    def get_config(self) -> dict:
        return {
            "min_confidence": self.min_confidence,
            "start_time":     self.start_time,
            "end_time":       self.end_time,
            "properties":     {k: p.pattern for k, p in self._patterns.items()},
        }
