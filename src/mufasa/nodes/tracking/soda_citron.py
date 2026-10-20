"""Static object data association node backed by SODA-CitrON."""
import importlib
import math
from collections.abc import Callable, Iterator

import numpy as np
from shapely.geometry import Point

from mufasa.location import UncertainObservation
from mufasa.nodes.tracking.dbstream import DBSTREAMClusterer

# Same probability bounds as POM / StaticMap: keeps log-odds finite, so a
# 0.0 and a 1.0 detection in one cluster cannot fuse to NaN.
_PMIN = 1e-5
_PMAX = 1.0 - 1e-5

# Property read from each input detection to identify it in ``members``.
_MEMBER_ID_KEY = "id"

_METRICS = ("euclidean", "mahalanobis")
_ASSIGNMENTS = ("multi", "hard", "soft")


def _sorted_ids(ids: set) -> list:
    """Return detection IDs as a deterministic, JSON-serialisable list."""
    try:
        return sorted(ids)
    except TypeError:  # IDs of mixed, mutually unorderable types
        return sorted(ids, key=repr)


def _resolve_function(spec: Callable | str) -> Callable:
    """Return ``spec`` itself if callable, else import it from ``"module:qualname"``."""
    if callable(spec):
        return spec
    if isinstance(spec, str) and ":" in spec:
        module_name, _, qualname = spec.partition(":")
        obj = importlib.import_module(module_name)
        for attr in qualname.split("."):
            obj = getattr(obj, attr)
        if callable(obj):
            return obj
    raise TypeError(f"expected a callable or an import path 'module:qualname', got {spec!r}")


def _function_path(fn: Callable) -> str:
    """Return the import path of ``fn``, if importing it yields ``fn`` again."""
    path = f"{getattr(fn, '__module__', None)}:{getattr(fn, '__qualname__', None)}"
    try:
        if _resolve_function(path) is fn:
            return path
    except (ImportError, AttributeError, TypeError):
        pass
    raise TypeError(
        f"confidence_to_weight {fn!r} cannot be stored in a graph config. "
        "Define it at module level, or pass its import path as 'module:qualname'."
    )


class SodaCitronClusterer(DBSTREAMClusterer):
    """Associate detections of static objects using SODA-CitrON.

    SODA-CitrON (Nausner et al., FUSION 2026, arXiv:2602.22243) extends
    DBSTREAM for static objects observed by heterogeneous sensors:

    - each detection is weighted by its confidence, optionally transformed by
      ``confidence_to_weight``, so ``minimum_weight`` acts as a
      confidence-aware track-initiation threshold;
    - cluster positions and covariances are estimated with an information
      filter, so precise detections count more than imprecise ones;
    - every object keeps a persistent ``cluster_id`` across flushes.

    Fading and cleanup are disabled because static objects never move.

    Windowing, late-detection clamping and end-of-stream handling are inherited
    unchanged from :class:`DBSTREAMClusterer`. After each flush one
    :class:`UncertainObservation` is emitted per object, carrying the fused
    position, covariance and confidence, plus these ``properties``:

    ``cluster_id``
        Persistent object ID (ULID string).
    ``weight``
        Accumulated detection weight.
    ``members``
        Sorted list of the IDs of the associated detections, taken from each
        input's ``properties["id"]`` (a ULID is generated when absent). IDs
        must be hashable.

    Parameters
    ----------
    timeout_s:
        Scan window duration in seconds.
    clustering_threshold:
        Gate radius ``r`` for associating a detection with a micro-cluster.
        With ``metric="euclidean"`` it is in CRS units (metres for UTM); the
        paper uses 1.1 m for sensors with sub-metre accuracy. With
        ``metric="mahalanobis"`` it is in standard deviations (2D: 2.45 ≈ 95 %,
        3.03 ≈ 99 %), so the default of 50 must then be set explicitly.
    intersection_factor:
        Shared-density threshold ``α`` for connecting micro-clusters.
    minimum_weight:
        Accumulated weight ``w_min`` an object needs before it is emitted.
        Raising it rejects more clutter at the cost of missed objects. With
        the default weights this is the summed confidence of the detections.
    confidence_to_weight:
        Optional function mapping a detection's confidence to its weight,
        given as a callable or as an import path ``"module:qualname"``. It
        receives the observation's confidence unchanged and must return a
        finite weight >= 0. ``None`` uses the confidence itself as the weight.
        To be stored in a graph config, the function must be importable, so
        define it at module level rather than as a lambda or closure.
    metric:
        Gating distance: ``"euclidean"`` (as in the paper) or
        ``"mahalanobis"``, which accounts for the uncertainty of cluster and,
        with ``use_innovation_cov``, detection.
    use_innovation_cov:
        Measure Mahalanobis distances with the innovation covariance
        ``P + R`` instead of the cluster covariance ``P`` alone. Used for
        gating with ``metric="mahalanobis"`` and always for the association
        weights of ``"hard"`` and ``"soft"`` assignment.
    collapse_threshold:
        Euclidean distance in CRS units below which two updated micro-cluster
        centres are considered collapsed and their update is reverted.
        ``None`` uses ``clustering_threshold`` for ``assignment="multi"`` and
        disables it otherwise; set it explicitly with
        ``metric="mahalanobis"``.
    assignment:
        How a detection gated to several micro-clusters is shared out:
        ``"multi"`` fuses it fully into each (as in the paper and DBSTREAM),
        ``"hard"`` only into the closest, and ``"soft"`` splits it by
        normalised association weights.
    """

    _input_types = [UncertainObservation]
    _output_type = UncertainObservation
    _required_modules = {**DBSTREAMClusterer._required_modules, "ulid": "python-ulid"}

    def __init__(
        self,
        timeout_s: float = 1.0,
        clustering_threshold: float = 50.0,
        intersection_factor: float = 0.3,
        minimum_weight: float = 1.0,
        confidence_to_weight: Callable[[float], float] | str | None = None,
        metric: str = "euclidean",
        use_innovation_cov: bool = True,
        collapse_threshold: float | None = None,
        assignment: str = "multi",
    ) -> None:
        super().__init__(
            timeout_s=timeout_s,
            clustering_threshold=clustering_threshold,
            fading_factor=0.0,
            cleanup_interval=1,
            intersection_factor=intersection_factor,
            minimum_weight=minimum_weight,
        )
        if metric not in _METRICS:
            raise ValueError(f"metric must be one of {_METRICS}, got {metric!r}")
        if collapse_threshold is not None and collapse_threshold < 0:
            raise ValueError("collapse_threshold must be >= 0 or None")
        if assignment not in _ASSIGNMENTS:
            raise ValueError(f"assignment must be one of {_ASSIGNMENTS}, got {assignment!r}")
        self.confidence_to_weight = confidence_to_weight
        self.metric = metric
        self.use_innovation_cov = use_innovation_cov
        self.collapse_threshold = collapse_threshold
        self.assignment = assignment

    @property
    def confidence_to_weight(self) -> Callable[[float], float] | None:
        return self._confidence_to_weight

    @confidence_to_weight.setter
    def confidence_to_weight(self, fn: Callable[[float], float] | str | None) -> None:
        self._confidence_to_weight = None if fn is None else _resolve_function(fn)

    def get_config(self) -> dict:
        config = super().get_config()
        # Fixed by the algorithm, so not constructor arguments of this node.
        del config["fading_factor"], config["cleanup_interval"]
        fn = self._confidence_to_weight
        config.update(
            confidence_to_weight=None if fn is None else _function_path(fn),
            metric=self.metric,
            use_innovation_cov=self.use_innovation_cov,
            collapse_threshold=self.collapse_threshold,
            assignment=self.assignment,
        )
        return config

    # ------------------------------------------------------------------
    # DBSTREAMClusterer hooks
    # ------------------------------------------------------------------

    def _build_model(self):
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        return SodaCitron(
            clustering_threshold=self.clustering_threshold,
            intersection_factor=self.intersection_factor,
            minimum_weight=self.minimum_weight,
            metric=self.metric,
            use_innovation_cov=self.use_innovation_cov,
            collapse_threshold=self.collapse_threshold,
            assignment=self.assignment,
        )

    def _weight(self, confidence: float) -> float:
        fn = self._confidence_to_weight
        weight = confidence if fn is None else float(fn(confidence))
        if not (math.isfinite(weight) and weight >= 0):
            raise ValueError(
                f"detection weight must be finite and >= 0, got {weight!r} "
                f"for confidence {confidence!r}"
            )
        return weight

    def _learn(self, obs: UncertainObservation) -> None:
        pt = obs.geometry.centroid
        weight = self._weight(float(obs.confidence))
        confidence = min(max(float(obs.confidence), _PMIN), _PMAX)
        sample_id = obs.properties.get(_MEMBER_ID_KEY)
        if sample_id is None:
            from ulid import ULID
            sample_id = str(ULID())
        self._model.learn_one(
            np.array([pt.x, pt.y]),
            confidence,
            obs.covariance,
            w=weight,
            id=sample_id,
        )

    def _cluster_locations(self, timestamp: float) -> Iterator[UncertainObservation]:
        for cluster in self._model.clusters.values():
            x, y = cluster.center
            yield UncertainObservation(
                geometry=Point(float(x), float(y)),
                timestamp=timestamp,
                confidence=float(cluster.conf),
                covariance=cluster.cov,
                properties={
                    "cluster_id": str(cluster.id),
                    "weight": float(cluster.weight),
                    "members": _sorted_ids(cluster.members),
                },
            )
