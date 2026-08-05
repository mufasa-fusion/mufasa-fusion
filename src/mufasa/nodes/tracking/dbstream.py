"""Streaming spatial clustering node backed by DBSTREAM (river)."""
import dataclasses

from shapely.geometry import Point

from mufasa.location import Location
from mufasa.node import Node


class DBSTREAMClusterer(Node):

    _input_types = [Location]
    _output_type = Location
    """Cluster Locations spatially using DBSTREAM from the river library.

    Unlike a fresh DBSCAN run per window, the DBSTREAM model persists across
    flushes: clusters that keep receiving nearby locations stay alive; clusters
    with no recent locations fade out via the built-in fading mechanism.

    Locations are buffered for ``timeout_s`` seconds then fed to the model in
    one batch.  After each flush one Location is emitted per active cluster,
    positioned at the cluster centre.

    Late or timestampless locations are clamped to the current window start
    and included rather than dropped.

    Parameters
    ----------
    timeout_s:
        Scan window duration in seconds.
    clustering_threshold:
        Maximum radius of a micro-cluster in CRS units (metres for UTM).
        This is the primary tuning parameter — set it to the approximate
        spatial scale at which two detections should be considered the same
        object.
    fading_factor:
        Controls how quickly micro-clusters lose weight between updates.
        Higher values cause faster decay of inactive clusters.
    cleanup_interval:
        Number of updates between pruning of micro-clusters whose weight
        has fallen below ``minimum_weight``.
    intersection_factor:
        Controls when two overlapping micro-clusters are merged (fraction
        of the sum of their radii).
    minimum_weight:
        Micro-clusters with weight below this value are removed during
        cleanup.
    """

    def __init__(
        self,
        timeout_s: float = 1.0,
        clustering_threshold: float = 50.0,
        fading_factor: float = 0.01,
        cleanup_interval: int = 4,
        intersection_factor: float = 0.3,
        minimum_weight: float = 1.0,
    ) -> None:
        super().__init__()
        if timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if clustering_threshold <= 0:
            raise ValueError("clustering_threshold must be > 0")
        self.timeout_s = timeout_s
        self.clustering_threshold = clustering_threshold
        self.fading_factor = fading_factor
        self.cleanup_interval = cleanup_interval
        self.intersection_factor = intersection_factor
        self.minimum_weight = minimum_weight

        self._buffer: list[Location] = []
        self._timeout_start: float | None = None
        self._model = None  # river DBSTREAM, lazily initialised and persisted

    def configure(self, crs, bbox, resolution) -> None:
        try:
            import river  # noqa: F401
        except ImportError:
            raise ImportError(
                "DBSTREAMClusterer requires river. "
                "Install it with: pip install \"mufasa[tracking]\""
            )

        from river.cluster import DBSTREAM
        self._model = DBSTREAM(
            clustering_threshold=self.clustering_threshold,
            fading_factor=self.fading_factor,
            cleanup_interval=self.cleanup_interval,
            intersection_factor=self.intersection_factor,
            minimum_weight=self.minimum_weight,
        )
        super().configure(crs, bbox, resolution)

    # ------------------------------------------------------------------
    # Node interface
    # ------------------------------------------------------------------

    def process(self, obs: Location) -> None:
        t = obs.timestamp

        if t is None or self._timeout_start is None:
            if t is None and self._timeout_start is not None:
                obs = dataclasses.replace(obs, timestamp=self._timeout_start)
            if t is not None and self._timeout_start is None:
                self._timeout_start = t
            self._buffer.append(obs)
            return

        if t < self._timeout_start:
            obs = dataclasses.replace(obs, timestamp=self._timeout_start)
            self._buffer.append(obs)
            return

        if t >= self._timeout_start + self.timeout_s:
            self._flush()
            while self._timeout_start + self.timeout_s <= t:
                self._timeout_start += self.timeout_s

        self._buffer.append(obs)

    def flush(self) -> None:
        if self._buffer:
            self._flush()

    def reset(self) -> None:
        self._buffer.clear()
        self._timeout_start = None
        self._model = None

    def get_config(self) -> dict:
        return {
            "timeout_s": self.timeout_s,
            "clustering_threshold": self.clustering_threshold,
            "fading_factor": self.fading_factor,
            "cleanup_interval": self.cleanup_interval,
            "intersection_factor": self.intersection_factor,
            "minimum_weight": self.minimum_weight,
        }

    # ------------------------------------------------------------------
    # Internal clustering logic
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        if not self._buffer:
            return

        locations = sorted(self._buffer, key=lambda e: e.timestamp)
        self._buffer.clear()

        scan_time = locations[-1].timestamp

        for l in locations:
            pt = l.geometry.centroid
            self._model.learn_one({"x": pt.x, "y": pt.y})

        self._emit_cluster_locations(scan_time)

    def _emit_cluster_locations(self, timestamp: float) -> None:
        centers = self._model.centers
        if not centers:
            return

        for cluster_id, center in centers.items():
            cluster_location = Location(
                geometry=Point(center["x"], center["y"]),
                timestamp=timestamp,
                properties={"cluster_id": int(cluster_id)},
            )
            for succ in self._successors:
                succ.process(cluster_location)
