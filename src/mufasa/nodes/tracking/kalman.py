"""Multi-target Kalman tracker node backed by Stone Soup."""
import warnings
from datetime import datetime, timedelta, timezone
import dataclasses

import numpy as np
from shapely.geometry import Point

from mufasa.location import Observation, Location
from mufasa.node import Node

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _to_dt(t: float) -> datetime:
    return _EPOCH + timedelta(seconds=t)


def _from_dt(dt: datetime) -> float:
    return (dt - _EPOCH).total_seconds()


class KalmanTracker(Node):

    _input_types = [Location]
    _output_type = Observation
    """Multi-target tracker wrapping Stone Soup's Kalman filter pipeline.

    Locations are buffered for ``buffer_s`` seconds before being dispatched
    to the tracker as a single scan, so detections from unsynchronised upstream
    nodes (e.g. two independent Threshold nodes) are naturally merged.

    Locations arriving up to ``max_late_s`` seconds before the current buffer
    window start are accepted; their timestamp is clamped to the window start
    so Stone Soup never receives a backwards-in-time update.  Locations older
    than that are dropped with a warning.

    Emits one Observation per confirmed track per scan, carrying estimated position,
    velocity, and a stable ``track_id`` in ``properties``.

    Parameters
    ----------
    buffer_s:
        Scan window duration in seconds.
    max_late_s:
        Grace period for late-arriving locations.
    process_noise:
        Power spectral density of the acceleration noise in m²·s⁻³.
        Rule of thumb: ``expected_velocity_change_m_s ** 2 / buffer_s``.
        E.g. for ±1 m/s velocity change per 1 s scan use 1.0.
    measurement_noise:
        Standard deviation of position measurement noise in CRS units (metres).
    max_missed_frames:
        Delete a track after this many consecutive scans with no detection.
    min_detections_to_confirm:
        Minimum detections in consecutive scans to confirm a new track.
    """

    def __init__(
        self,
        buffer_s: float = 1.0,
        max_late_s: float = 5.0,
        process_noise: float = 0.05,
        measurement_noise: float = 10.0,
        max_missed_frames: int = 3,
        min_detections_to_confirm: int = 1,
    ) -> None:
        super().__init__()
        if buffer_s <= 0:
            raise ValueError("buffer_s must be > 0")
        if max_late_s < 0:
            raise ValueError("max_late_s must be >= 0")
        self.buffer_s = buffer_s
        self.max_late_s = max_late_s
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.max_missed_frames = max_missed_frames
        self.min_detections_to_confirm = min_detections_to_confirm

        self._buffer: list[Observation] = []
        self._buffer_start: float | None = None
        self._tracks: set = set()
        self._ss: dict = {}

    # ------------------------------------------------------------------
    # Node interface
    # ------------------------------------------------------------------

    def configure(self, crs, bbox, resolution) -> None:
        try:
            import stonesoup  # noqa: F401 — raises if not installed
        except ImportError:
            raise ImportError(
                "KalmanTracker requires stonesoup. "
                "Install it with: pip install \"mufasa[tracking]\""
            ) from None

        from stonesoup.dataassociator.neighbour import GNNWith2DAssignment
        from stonesoup.deleter.time import UpdateTimeStepsDeleter
        from stonesoup.hypothesiser.distance import DistanceHypothesiser
        from stonesoup.initiator.simple import MultiMeasurementInitiator
        from stonesoup.measures import Mahalanobis
        from stonesoup.models.measurement.linear import LinearGaussian
        from stonesoup.models.transition.linear import (
            CombinedLinearGaussianTransitionModel,
            ConstantVelocity,
        )
        from stonesoup.predictor.kalman import KalmanPredictor
        from stonesoup.types.array import CovarianceMatrix, StateVector
        from stonesoup.types.state import GaussianState
        from stonesoup.updater.kalman import KalmanUpdater
        
        transition_model = CombinedLinearGaussianTransitionModel(
            [ConstantVelocity(self.process_noise), ConstantVelocity(self.process_noise)]
        )
        measurement_model = LinearGaussian(
            ndim_state=4,
            mapping=[0, 2],
            noise_covar=np.diag([self.measurement_noise**2, self.measurement_noise**2]),
        )

        predictor = KalmanPredictor(transition_model)
        updater = KalmanUpdater(measurement_model)
        hypothesiser = DistanceHypothesiser(
            predictor, updater, measure=Mahalanobis(), missed_distance=1e6
        )
        data_associator = GNNWith2DAssignment(hypothesiser)

        pos_var = (self.measurement_noise * 100) ** 2
        vel_var = (self.process_noise * 1000) ** 2
        prior_state = GaussianState(
            state_vector=StateVector([0, 0, 0, 0]),
            covar=CovarianceMatrix(np.diag([pos_var, vel_var, pos_var, vel_var])),
            timestamp=_EPOCH,
        )
        initiator = MultiMeasurementInitiator(
            prior_state=prior_state,
            measurement_model=measurement_model,
            deleter=UpdateTimeStepsDeleter(time_steps_since_update=1),
            data_associator=GNNWith2DAssignment(hypothesiser),
            updater=updater,
            min_points=self.min_detections_to_confirm,
            updates_only=False,
        )
        deleter = UpdateTimeStepsDeleter(time_steps_since_update=self.max_missed_frames)

        self._ss = {
            "predictor": predictor,
            "updater": updater,
            "data_associator": data_associator,
            "initiator": initiator,
            "deleter": deleter,
        }
        super().configure(crs, bbox, resolution)

    # ------------------------------------------------------------------
    # Node interface
    # ------------------------------------------------------------------

    def process(self, obs: Observation) -> None:
        t = obs.timestamp

        if self._buffer_start is None:
            self._buffer_start = t
            self._buffer.append(obs)
            return

        if t < self._buffer_start:
            lag = self._buffer_start - t
            if lag <= self.max_late_s:
                obs = dataclasses.replace(obs, timestamp=self._buffer_start)
                self._buffer.append(obs)
            else:
                warnings.warn(
                    f"KalmanTracker: dropped late Observation at t={t:.2f}s "
                    f"({lag:.2f}s behind buffer_start={self._buffer_start:.2f}s, "
                    f"max_late_s={self.max_late_s})"
                )
            return

        if t >= self._buffer_start + self.buffer_s:
            self._dispatch_scan()
            self._buffer_start += self.buffer_s
            while self._buffer_start + self.buffer_s <= t:
                self._dispatch_scan()  # empty scan — ticks max_missed_frames
                self._buffer_start += self.buffer_s

        self._buffer.append(obs)

    def flush(self) -> None:
        """Emit any detections remaining in the buffer at end of stream."""
        if self._buffer:
            self._dispatch_scan()

    def reset(self) -> None:
        self._buffer.clear()
        self._buffer_start = None
        self._tracks = set()

    def get_config(self) -> dict:
        return {
            "buffer_s": self.buffer_s,
            "max_late_s": self.max_late_s,
            "process_noise": self.process_noise,
            "measurement_noise": self.measurement_noise,
            "max_missed_frames": self.max_missed_frames,
            "min_detections_to_confirm": self.min_detections_to_confirm,
        }

    # ------------------------------------------------------------------
    # Internal tracking logic
    # ------------------------------------------------------------------

    def _dispatch_scan(self) -> None:
        """Process the current buffer as one scan and clear it.

        Called both by process() when a window expires and by flush() at
        end-of-stream. With an empty buffer (gap between windows) it still
        runs a scan with no detections so max_missed_frames ticks correctly.
        """
        if not self._buffer and not self._tracks:
            return  # nothing to do before any track has ever been initiated

        from stonesoup.types.array import StateVector
        from stonesoup.types.detection import Detection

        locations = sorted(self._buffer, key=lambda e: e.timestamp)
        self._buffer.clear()

        detections = set()
        for e in locations:
            pt = e.geometry.centroid
            detections.add(
                Detection(
                    StateVector([[pt.x], [pt.y]]),
                    timestamp=_to_dt(e.timestamp),
                )
            )

        scan_time = _to_dt(locations[-1].timestamp) if locations else _to_dt(self._buffer_start + self.buffer_s)
        self._run_scan(detections, scan_time)

    def _run_scan(self, detections: set, timestamp: datetime) -> None:
        associations = self._ss["data_associator"].associate(self._tracks, detections, timestamp)

        associated_detections = set()
        for track, hypothesis in associations.items():
            if hypothesis.measurement:
                posterior = self._ss["updater"].update(hypothesis)
                track.append(posterior)
                associated_detections.add(hypothesis.measurement)
            else:
                prediction = self._ss["predictor"].predict(track.state, timestamp=timestamp)
                track.append(prediction)

        unassociated = detections - associated_detections
        new_tracks = self._ss["initiator"].initiate(unassociated, timestamp)
        self._tracks |= new_tracks

        deleted = self._ss["deleter"].delete_tracks(self._tracks)
        self._tracks -= deleted

        self._emit_track_observations(timestamp)

    def _emit_track_observations(self, timestamp: datetime) -> None:
        for track in self._tracks:
            state = track.state
            sv = state.state_vector
            x, vx = float(sv[0]), float(sv[1])
            y, vy = float(sv[2]), float(sv[3])

            pos_std = float(np.sqrt(state.covar[0, 0] + state.covar[2, 2]))
            confidence = float(np.exp(-pos_std / (self.measurement_noise * 10))) # Should be looked at in the future since original confidence is lost

            track_observation = Observation(
                geometry=Point(x, y),
                timestamp=_from_dt(timestamp),
                confidence=min(max(confidence, 0.0), 1.0),
                properties={
                    "track_id": str(track.id),
                    "velocity_x": vx,
                    "velocity_y": vy,
                },
            )
            for succ in self._successors:
                succ.process(track_observation)
