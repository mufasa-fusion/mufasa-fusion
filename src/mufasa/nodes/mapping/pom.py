import numpy as np
from scipy.special import logit

from mufasa.location import Observation
from mufasa.map import BayesianMap
from mufasa.nodes.mapping.heat import HeatMap

_PMIN = 1e-5
_PMAX = 1.0 - 1e-5


class POM(HeatMap):
    """Probability Occupancy Map: Bayesian log-odds accumulation with exponential decay.

    Internal state and ``BayesianMap.data`` are both in log-odds space.
    Use ``map.probabilities`` to obtain values in [0, 1]. Produces
    ``BayesianMap`` so that fusion nodes can enforce compatible wiring.
    """

    _map_class = BayesianMap
    _input_types = [Observation]
    _output_type = BayesianMap

    def __init__(self, decay_s: float, prior: float = 0.5) -> None:
        """
        Parameters
        ----------
        decay_s : float
            Exponential decay time constant in seconds.
        prior : float
            Sensor baseline confidence.  Observations with ``confidence == prior``
            are neutral (zero log-odds contribution).  Above ``prior`` increases
            the map; below decreases it.  The map itself always starts at
            probability 0.5 (unknown) — use a ``StaticMap`` + ``BayesianFusion``
            to set a spatial prior on occupancy.
        """
        super().__init__(decay_s)
        if not 0.0 < prior < 1.0:
            raise ValueError("prior must be in (0, 1)")
        self.prior = prior

    # ------------------------------------------------------------------
    # HeatMap hooks
    # ------------------------------------------------------------------

    def _init_data(self, shape: tuple) -> np.ndarray:
        return np.zeros(shape, dtype=np.float64)

    def _decay(self, delta_t_s: float) -> None:
        self._data *= np.exp(-delta_t_s / self.decay_s)

    def _model_update(self, mask: np.ndarray, confidence: float) -> None:
        prior_lo = logit(np.clip(self.prior, _PMIN, _PMAX))
        self._data[mask] += logit(np.clip(confidence, _PMIN, _PMAX)) - prior_lo

    def get_config(self) -> dict:
        return {"decay_s": self.decay_s, "prior": self.prior}
