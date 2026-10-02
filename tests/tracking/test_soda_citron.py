"""Tests for SodaCitronClusterer and the integrated SODA-CitrON algorithm."""
import json
import math

import numpy as np
import pytest
from scipy.special import expit, logit
from pyproj import Transformer
from shapely.geometry import Point
from ulid import ULID

from mufasa import Graph
from mufasa.io.inputs.base import InputNode
from mufasa.io.inputs.python_object import LocationInput
from mufasa.io.outputs.python_object import LocationOutput
from mufasa.location import Location, Observation, UncertainObservation
from mufasa.nodes.tracking.dbstream import DBSTREAMClusterer
from mufasa.nodes.tracking.soda_citron import SodaCitronClusterer
from mufasa.nodes.util.filter import ObservationFilter
from mufasa.registry import NODE_REGISTRY

R = np.eye(2)  # 1 m² isotropic position covariance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class LocationCollector:
    _successors = []

    def __init__(self):
        self.received: list[Location] = []

    def process(self, obs: Location) -> None:
        self.received.append(obs)


def make_clusterer(**kwargs) -> tuple[SodaCitronClusterer, LocationCollector]:
    # With confidences as weights, a single detection of confidence >= 0.9
    # initiates an object.
    kwargs.setdefault("clustering_threshold", 5.0)
    kwargs.setdefault("minimum_weight", 0.9)
    clusterer = SodaCitronClusterer(**kwargs)
    clusterer.configure(crs=None, bbox=None, resolution=None)
    collector = LocationCollector()
    clusterer._successors = [collector]
    return clusterer, collector


def detection(x, y, t, confidence=0.95, covariance=R, **properties) -> UncertainObservation:
    return UncertainObservation(
        geometry=Point(x, y),
        timestamp=t,
        confidence=confidence,
        covariance=covariance,
        properties=properties,
    )


def push(clusterer, *detections) -> None:
    for d in detections:
        clusterer.process(d)


def last_flush(received: list) -> list[UncertainObservation]:
    """Objects emitted by the most recent flush (they share its scan time)."""
    if not received:
        return []
    t = received[-1].timestamp
    return [o for o in received if o.timestamp == t]


_CUSTOM = dict(
    timeout_s=2.0, clustering_threshold=3.0, intersection_factor=0.5,
    minimum_weight=3.0, confidence_to_weight="math:sqrt",
    metric="mahalanobis", use_innovation_cov=False, collapse_threshold=0.5,
    assignment="soft",
)


class _UncertainSource(InputNode):
    _output_type = UncertainObservation
    def items(self): return []
    def get_config(self): return {}


class _ObservationSource(InputNode):
    _output_type = Observation
    def items(self): return []
    def get_config(self): return {}


# ---------------------------------------------------------------------------
# Confidence-to-weight transform
# ---------------------------------------------------------------------------

def paper_weight(confidence: float) -> float:
    """Eq. (8) of the SODA-CitrON paper with w_max = 10 and beta = 6."""
    return 10.0 * math.expm1(6.0 * confidence) / math.expm1(6.0)


class TestConfidenceToWeight:
    def test_default_weight_is_confidence(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, confidence=0.7), detection(0, 0, 0.1, confidence=0.8))
        clusterer.flush()
        assert collector.received[0].properties["weight"] == pytest.approx(1.5)

    def test_callable_is_applied(self):
        clusterer, collector = make_clusterer(confidence_to_weight=paper_weight, minimum_weight=4.0)
        push(clusterer, detection(0, 0, 0.0, confidence=0.95))
        clusterer.flush()
        assert collector.received[0].properties["weight"] == pytest.approx(paper_weight(0.95))

    def test_import_path_is_resolved(self):
        clusterer = SodaCitronClusterer(confidence_to_weight="math:sqrt")
        assert clusterer.confidence_to_weight is math.sqrt

    def test_attribute_assignment_resolves_import_path(self):
        clusterer = SodaCitronClusterer()
        clusterer.confidence_to_weight = "math:sqrt"
        assert clusterer.confidence_to_weight is math.sqrt
        clusterer.confidence_to_weight = None
        assert clusterer.confidence_to_weight is None

    def test_function_receives_unclipped_confidence(self):
        seen = []

        def record(confidence):
            seen.append(confidence)
            return 1.0

        clusterer, _ = make_clusterer(confidence_to_weight=record)
        push(clusterer, detection(0, 0, 0.0, confidence=1.0), detection(0, 0, 0.1, confidence=0.0))
        clusterer.flush()
        assert seen == [1.0, 0.0]

    def test_zero_confidence_detection_adds_no_default_weight(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, confidence=0.95), detection(0, 0, 0.1, confidence=0.0))
        clusterer.flush()
        assert collector.received[0].properties["weight"] == pytest.approx(0.95)

    @pytest.mark.parametrize("weight", [-1.0, math.nan, math.inf])
    def test_invalid_weight_raises(self, weight):
        clusterer, _ = make_clusterer(confidence_to_weight=lambda c: weight)
        push(clusterer, detection(0, 0, 0.0))
        with pytest.raises(ValueError, match="weight must be finite and >= 0"):
            clusterer.flush()

    def test_confidence_outside_unit_interval_is_rejected_by_default(self):
        clusterer, _ = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, confidence=-0.5))
        with pytest.raises(ValueError, match="weight must be finite and >= 0"):
            clusterer.flush()

    @pytest.mark.parametrize("spec", [42, "math.sqrt", "math:no_such_function"])
    def test_invalid_spec_raises(self, spec):
        with pytest.raises((TypeError, AttributeError)):
            SodaCitronClusterer(confidence_to_weight=spec)

    def test_unknown_module_raises(self):
        with pytest.raises(ImportError):
            SodaCitronClusterer(confidence_to_weight="no_such_module_xyz:f")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TestSodaCitronClustererTypes:
    def test_is_dbstream_clusterer(self):
        assert issubclass(SodaCitronClusterer, DBSTREAMClusterer)

    def test_accepts_uncertain_observation(self):
        assert UncertainObservation in SodaCitronClusterer().input_types

    def test_does_not_accept_plain_observation(self):
        assert not any(issubclass(Observation, t) for t in SodaCitronClusterer().input_types)

    def test_wiring_plain_observation_source_raises(self):
        with pytest.raises(TypeError):
            SodaCitronClusterer()(_ObservationSource())

    def test_wiring_uncertain_observation_source_succeeds(self):
        SodaCitronClusterer()(_UncertainSource())

    def test_output_type_is_uncertain_observation(self):
        assert SodaCitronClusterer().output_type is UncertainObservation

    def test_output_feeds_observation_nodes(self):
        ObservationFilter()(SodaCitronClusterer()(_UncertainSource()))


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestSodaCitronClustererInit:
    def test_default_params_stored(self):
        c = SodaCitronClusterer()
        assert c.timeout_s == pytest.approx(1.0)
        assert c.clustering_threshold == pytest.approx(50.0)
        assert c.intersection_factor == pytest.approx(0.3)
        assert c.minimum_weight == pytest.approx(1.0)
        assert c.confidence_to_weight is None
        assert c.metric == "euclidean"
        assert c.use_innovation_cov is True
        assert c.collapse_threshold is None
        assert c.assignment == "multi"

    def test_fading_and_cleanup_disabled(self):
        c = SodaCitronClusterer()
        assert c.fading_factor == 0.0
        assert c.cleanup_interval == 1

    def test_custom_params_stored(self):
        c = SodaCitronClusterer(**_CUSTOM)
        for name, value in _CUSTOM.items():
            if name == "confidence_to_weight":
                assert c.confidence_to_weight is math.sqrt
            else:
                assert getattr(c, name) == value

    @pytest.mark.parametrize("kwargs", [
        {"timeout_s": 0.0},
        {"clustering_threshold": 0.0},
        {"metric": "manhattan"},
        {"assignment": "greedy"},
        {"collapse_threshold": -1.0},
    ])
    def test_invalid_params_raise(self, kwargs):
        with pytest.raises(ValueError):
            SodaCitronClusterer(**kwargs)

    def test_model_is_soda_citron(self):
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        clusterer, _ = make_clusterer()
        assert isinstance(clusterer._model, SodaCitron)

    def test_parameters_reach_model(self):
        clusterer = SodaCitronClusterer(**_CUSTOM)
        clusterer.configure(crs=None, bbox=None, resolution=None)
        model = clusterer._model
        assert model.clustering_threshold == _CUSTOM["clustering_threshold"]
        assert model.intersection_factor == _CUSTOM["intersection_factor"]
        assert model.minimum_weight == _CUSTOM["minimum_weight"]
        assert model.metric == _CUSTOM["metric"]
        assert model.use_innovation_cov == _CUSTOM["use_innovation_cov"]
        assert model.collapse_threshold == _CUSTOM["collapse_threshold"]
        assert model.assignment == _CUSTOM["assignment"]


# ---------------------------------------------------------------------------
# Buffering (inherited from DBSTREAMClusterer)
# ---------------------------------------------------------------------------

class TestSodaCitronClustererBuffering:
    def test_no_output_within_same_window(self):
        clusterer, collector = make_clusterer(timeout_s=5.0)
        push(clusterer, detection(0, 0, 0.0), detection(0, 0, 1.0))
        assert collector.received == []

    def test_flush_drains_buffer(self):
        clusterer, collector = make_clusterer(timeout_s=5.0)
        push(clusterer, detection(0, 0, 0.0))
        clusterer.flush()
        assert len(collector.received) == 1

    def test_new_window_triggers_flush(self):
        clusterer, collector = make_clusterer(timeout_s=1.0)
        push(clusterer, detection(0, 0, 0.0))
        assert collector.received == []
        push(clusterer, detection(0, 0, 1.5))
        assert len(collector.received) == 1

    def test_empty_flush_emits_nothing(self):
        clusterer, collector = make_clusterer()
        clusterer.flush()
        assert collector.received == []

    def test_late_detection_clamped_to_window_start(self):
        clusterer, collector = make_clusterer(timeout_s=1.0)
        push(clusterer, detection(0, 0, 5.0), detection(0, 0, 3.0))
        clusterer.flush()
        assert collector.received
        assert all(o.timestamp >= 5.0 for o in collector.received)


# ---------------------------------------------------------------------------
# State estimation
# ---------------------------------------------------------------------------

class TestSodaCitronClustererEstimation:
    def test_output_is_uncertain_observation_with_point_geometry(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(10, 20, 0.0))
        clusterer.flush()
        (obj,) = collector.received
        assert isinstance(obj, UncertainObservation)
        assert isinstance(obj.geometry, Point)
        assert (obj.geometry.x, obj.geometry.y) == pytest.approx((10, 20))

    def test_single_confident_detection_initiates_object(self):
        # weight 0.95 >= minimum_weight 0.9
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, confidence=0.95))
        clusterer.flush()
        assert len(collector.received) == 1

    def test_single_low_confidence_detection_is_rejected(self):
        # weight 0.5 < minimum_weight 0.9: treated as clutter
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, confidence=0.5))
        clusterer.flush()
        assert collector.received == []

    def test_many_low_confidence_detections_initiate_object(self):
        clusterer, collector = make_clusterer()
        push(clusterer, *[detection(0, 0, 0.1 * i, confidence=0.5) for i in range(10)])
        clusterer.flush()
        (obj,) = collector.received
        assert obj.properties["weight"] == pytest.approx(10 * 0.5)

    def test_two_separated_groups_produce_two_objects(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0), detection(100, 0, 0.1),
             detection(0, 0, 0.2), detection(100, 0, 0.3))
        clusterer.flush()
        assert len({o.properties["cluster_id"] for o in collector.received}) == 2

    def test_position_is_information_weighted(self):
        # A precise and an imprecise detection 4 m apart: the estimate stays
        # next to the precise one instead of at the midpoint.
        clusterer, collector = make_clusterer()
        push(clusterer,
             detection(0, 0, 0.0, covariance=0.01 * R),
             detection(4, 0, 0.1, covariance=4.0 * R))
        clusterer.flush()
        (obj,) = collector.received
        assert abs(obj.geometry.x) < 0.1

    def test_single_detection_keeps_its_covariance(self):
        clusterer, collector = make_clusterer()
        cov = np.array([[2.0, 0.5], [0.5, 1.0]])
        push(clusterer, detection(0, 0, 0.0, covariance=cov))
        clusterer.flush()
        np.testing.assert_allclose(collector.received[0].covariance, cov)

    def test_covariance_shrinks_with_more_detections(self):
        traces = []
        for n in (1, 2, 5, 10):
            clusterer, collector = make_clusterer()
            push(clusterer, *[detection(0, 0, 0.01 * i) for i in range(n)])
            clusterer.flush()
            traces.append(np.trace(collector.received[0].covariance))
        assert all(a > b for a, b in zip(traces, traces[1:]))

    def test_confidence_is_fused_in_log_odds(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, confidence=0.9), detection(0, 0, 0.1, confidence=0.9))
        clusterer.flush()
        (obj,) = collector.received
        assert obj.confidence == pytest.approx(expit(2 * logit(0.9)))

    def test_extreme_confidences_do_not_produce_nan(self):
        # Unclipped, logit(1) + logit(0) = inf - inf = NaN.
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, confidence=1.0), detection(0, 0, 0.1, confidence=0.0))
        clusterer.flush()
        (obj,) = collector.received
        assert 0.0 <= obj.confidence <= 1.0


# ---------------------------------------------------------------------------
# Data association
# ---------------------------------------------------------------------------

class TestSodaCitronClustererAssociation:
    def test_cluster_id_is_ulid_string(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0))
        clusterer.flush()
        ULID.from_str(collector.received[0].properties["cluster_id"])

    def test_cluster_id_stable_across_flushes(self):
        clusterer, collector = make_clusterer(timeout_s=1.0)
        for i in range(5):
            push(clusterer, detection(0.1 * i, 0, 1.5 * i))
        clusterer.flush()
        timestamps = {o.timestamp for o in collector.received}
        assert len(timestamps) == 5
        assert len({o.properties["cluster_id"] for o in collector.received}) == 1

    def test_members_are_detection_ids(self):
        clusterer, collector = make_clusterer()
        push(clusterer, *[detection(0, 0, 0.1 * i, id=name) for i, name in enumerate("abc")])
        clusterer.flush()
        assert collector.received[0].properties["members"] == ["a", "b", "c"]

    def test_members_generated_when_id_missing(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0), detection(0, 0, 0.1))
        clusterer.flush()
        members = collector.received[0].properties["members"]
        assert len(members) == 2
        assert len(set(members)) == 2
        for member in members:
            ULID.from_str(member)

    def test_members_are_sorted(self):
        clusterer, collector = make_clusterer()
        push(clusterer, *[detection(0, 0, 0.1 * i, id=name) for i, name in enumerate("cab")])
        clusterer.flush()
        assert collector.received[0].properties["members"] == ["a", "b", "c"]

    def test_members_of_mixed_types_are_listed(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, id="a"), detection(0, 0, 0.1, id=1))
        clusterer.flush()
        assert sorted(map(str, collector.received[0].properties["members"])) == ["1", "a"]

    def test_falsy_id_is_kept(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, id=0))
        clusterer.flush()
        assert collector.received[0].properties["members"] == [0]

    def test_members_unique_after_fusing_micro_clusters_repeatedly(self):
        # Two micro-clusters bridged by shared detections are fused into one
        # object on every flush; its member list must not accumulate duplicates.
        clusterer, collector = make_clusterer(timeout_s=1.0, clustering_threshold=1.0)
        cov = 0.1 * R
        push(clusterer,
             detection(0.0, 0, 0.0, 0.9, cov, id="d0"),
             detection(1.2, 0, 0.1, 0.9, cov, id="d1"))
        ids = ["d0", "d1"]
        for window in range(4):
            for k in range(2):
                name = f"b{window}{k}"
                ids.append(name)
                push(clusterer, detection(0.6, 0, window * 1.5 + 0.2 + 0.1 * k, 0.9, cov, id=name))
        clusterer.flush()
        final = last_flush(collector.received)
        assert len(clusterer._model.micro_clusters) == 2
        assert len(final) == 1
        assert sorted(final[0].properties["members"]) == sorted(ids)

    def test_output_properties_are_json_serializable(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0, id="a"))
        clusterer.flush()
        json.dumps(collector.received[0].properties)


# ---------------------------------------------------------------------------
# Integrated algorithm
# ---------------------------------------------------------------------------

class TestSodaCitronAlgorithm:
    def _bridged_model(self):
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        model = SodaCitron(clustering_threshold=1.0, minimum_weight=0.5)
        for i, x in enumerate([0.0, 1.2, 0.6, 0.6, 0.6]):
            model.learn_one(np.array([x, 0.0]), 0.9, 0.1 * R, w=1.0, id=f"d{i}")
        return model

    def test_micro_clusters_are_dbstream_micro_clusters(self):
        from river.cluster.dbstream import DBSTREAMMicroCluster
        model = self._bridged_model()
        assert all(isinstance(mc, DBSTREAMMicroCluster) for mc in model.micro_clusters.values())

    def test_cluster_ids_are_ulids(self):
        model = self._bridged_model()
        assert all(isinstance(c.id, ULID) for c in model.clusters.values())

    def test_members_are_sets(self):
        model = self._bridged_model()
        assert all(isinstance(mc.members, set) for mc in model.micro_clusters.values())
        assert all(isinstance(c.members, set) for c in model.clusters.values())

    def test_reclustering_does_not_mutate_micro_cluster_members(self):
        model = self._bridged_model()
        before = {k: set(mc.members) for k, mc in model.micro_clusters.items()}
        for _ in range(3):
            model.clustering_is_up_to_date = False  # as after every learn_one
            (macro,) = model.clusters.values()
            assert macro.members == set().union(*before.values())
        assert {k: mc.members for k, mc in model.micro_clusters.items()} == before

    def test_single_micro_cluster_object_keeps_exact_state(self):
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        model = SodaCitron(minimum_weight=0.5)
        for c in (0.9, 0.8, 0.7):
            model.learn_one(np.array([0.0, 0.0]), c, 0.1 * R, w=1.0)
        (micro,) = model.micro_clusters.values()
        (macro,) = model.clusters.values()
        for name in ("center", "cov", "Y", "y", "lo_conf", "weight", "id"):
            np.testing.assert_array_equal(getattr(macro, name), getattr(micro, name))

    @pytest.mark.parametrize("order", ["AB", "BA"])
    def test_fused_confidence_does_not_saturate(self, order):
        # A: near-certain detections (log-odds ~46, beyond float64 expit range),
        # B: many low-confidence ones; neutral detections bridge the two.
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        model = SodaCitron(clustering_threshold=1.0, minimum_weight=0.5)
        groups = {"A": [(0.0, 1 - 1e-5)] * 4, "B": [(1.2, 0.01)] * 20}
        for g in order:
            for x, c in groups[g]:
                model.learn_one(np.array([x, 0.0]), c, 0.1 * R, w=1.0)
        for _ in range(8):
            model.learn_one(np.array([0.6, 0.0]), 0.5, 0.1 * R, w=1.0)
        total = sum(mc.lo_conf for mc in model.micro_clusters.values())
        (macro,) = model.clusters.values()
        assert macro.lo_conf == pytest.approx(total)
        assert macro.conf < 1e-10

    def test_fused_estimate_uses_information_filter(self):
        model = self._bridged_model()
        (macro,) = model.clusters.values()
        np.testing.assert_allclose(macro.cov, np.linalg.inv(macro.Y))
        np.testing.assert_allclose(macro.center, macro.cov @ macro.y)

    def test_fused_object_keeps_id_of_heavier_micro_cluster(self):
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        model = SodaCitron(clustering_threshold=1.0, minimum_weight=0.5)
        for x, w in [(0.0, 1.0), (1.2, 10.0), (0.6, 1.0), (0.6, 1.0), (0.6, 1.0)]:
            model.learn_one(np.array([x, 0.0]), 0.9, 0.1 * R, w=w)
        light, heavy = model.micro_clusters[0], model.micro_clusters[1]
        assert heavy.weight > light.weight
        (macro,) = model.clusters.values()
        assert macro.id == heavy.id

    def test_objects_need_minimum_weight_even_if_river_labels_everything(self, monkeypatch):
        # river < 0.24.1 (the only versions on Python 3.10) assigns a label to
        # every micro cluster, including clutter below the minimum weight.
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        model = SodaCitron(clustering_threshold=1.0, minimum_weight=4.0)
        model.learn_one(np.array([0.0, 0.0]), 0.95, R, w=5.0)
        model.learn_one(np.array([10.0, 0.0]), 0.5, R, w=1.0)
        monkeypatch.setattr(
            model, "_generate_labels", lambda adjacency: {i: i for i in model.micro_clusters}
        )
        (macro,) = model.clusters.values()
        assert macro.center == pytest.approx([0.0, 0.0])

    def test_fading_disabled(self):
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        assert SodaCitron().fading_factor == 0.0


# ---------------------------------------------------------------------------
# Gating metric and assignment modes
# ---------------------------------------------------------------------------

class TestSodaCitronGatingAndAssignment:
    @staticmethod
    def _model(**kwargs):
        from mufasa.nodes.tracking._soda_citron import SodaCitron
        kwargs.setdefault("minimum_weight", 0.5)
        return SodaCitron(**kwargs)

    def _two_clusters_and_shared_detection(self, assignment):
        # Micro-clusters at x=0 and x=1.2; a detection at x=0.4 gates to both
        # (Euclidean r=1) and is closer to the first.
        model = self._model(clustering_threshold=1.0, assignment=assignment)
        model.learn_one(np.array([0.0, 0.0]), 0.9, 0.1 * R, w=1.0, id="a")
        model.learn_one(np.array([1.2, 0.0]), 0.9, 0.1 * R, w=1.0, id="b")
        model.learn_one(np.array([0.4, 0.0]), 0.9, 0.1 * R, w=2.0, id="shared")
        return model.micro_clusters[0], model.micro_clusters[1]

    def test_multi_fuses_detection_into_every_gated_cluster(self):
        near, far = self._two_clusters_and_shared_detection("multi")
        assert (near.weight, far.weight) == (3.0, 3.0)
        assert "shared" in near.members and "shared" in far.members

    def test_hard_fuses_detection_into_closest_cluster_only(self):
        near, far = self._two_clusters_and_shared_detection("hard")
        assert (near.weight, far.weight) == (3.0, 1.0)
        assert "shared" in near.members and "shared" not in far.members
        np.testing.assert_array_equal(far.center, [1.2, 0.0])

    def test_soft_splits_detection_by_association_weight(self):
        near, far = self._two_clusters_and_shared_detection("soft")
        assert near.weight + far.weight == pytest.approx(1.0 + 1.0 + 2.0)
        assert near.weight > far.weight > 1.0

    @pytest.mark.parametrize("assignment, expected", [("multi", 1.0), ("hard", 0.0), ("soft", 0.0)])
    def test_collapse_threshold_default_depends_on_assignment(self, assignment, expected):
        model = self._model(clustering_threshold=1.0, assignment=assignment)
        assert model.collapse_threshold == expected

    def test_explicit_collapse_threshold_wins(self):
        assert self._model(assignment="soft", collapse_threshold=0.7).collapse_threshold == 0.7

    def test_mahalanobis_rejects_close_but_improbable_detection(self):
        # 0.5 m apart, but σ = 0.1 m: 3.5σ under the innovation covariance.
        for metric, expected_clusters in (("euclidean", 1), ("mahalanobis", 2)):
            model = self._model(clustering_threshold=1.0 if metric == "euclidean" else 3.0, metric=metric)
            model.learn_one(np.array([0.0, 0.0]), 0.9, 0.01 * R, w=1.0)
            model.learn_one(np.array([0.5, 0.0]), 0.9, 0.01 * R, w=1.0)
            assert len(model.micro_clusters) == expected_clusters, metric

    def test_mahalanobis_accepts_distant_but_probable_detection(self):
        # 2 m apart, but σ = 1 m: 1.4σ under the innovation covariance.
        for metric, expected_clusters in (("euclidean", 2), ("mahalanobis", 1)):
            model = self._model(clustering_threshold=1.0 if metric == "euclidean" else 3.0, metric=metric)
            model.learn_one(np.array([0.0, 0.0]), 0.9, R, w=1.0)
            model.learn_one(np.array([2.0, 0.0]), 0.9, R, w=1.0)
            assert len(model.micro_clusters) == expected_clusters, metric

    @pytest.mark.parametrize("use_innovation_cov, expected_clusters", [(True, 1), (False, 2)])
    def test_innovation_covariance_widens_gate(self, use_innovation_cov, expected_clusters):
        # d = 3.5σ with P + R, but 5σ with P alone; gate at 4σ.
        model = self._model(clustering_threshold=4.0, metric="mahalanobis",
                            use_innovation_cov=use_innovation_cov)
        model.learn_one(np.array([0.0, 0.0]), 0.9, 0.01 * R, w=1.0)
        model.learn_one(np.array([0.5, 0.0]), 0.9, 0.01 * R, w=1.0)
        assert len(model.micro_clusters) == expected_clusters

    def test_callable_metric_is_supported_by_algorithm(self):
        calls = []

        def metric(x, mc, meas_cov):
            calls.append(meas_cov)
            return float(np.abs(x - mc.center).max())  # Chebyshev distance

        model = self._model(clustering_threshold=1.0, metric=metric)
        model.learn_one(np.array([0.0, 0.0]), 0.9, R, w=1.0)
        model.learn_one(np.array([0.9, 0.9]), 0.9, R, w=1.0)  # Euclidean 1.27, Chebyshev 0.9
        assert len(model.micro_clusters) == 1
        assert calls and calls[0] is not None


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestSodaCitronClustererReset:
    def test_reset_clears_buffer(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0))
        clusterer.reset()
        clusterer.flush()
        assert collector.received == []

    def test_reset_clears_model(self):
        clusterer, _ = make_clusterer()
        push(clusterer, detection(0, 0, 0.0), detection(0, 0, 1.5))
        clusterer.reset()
        assert clusterer._model is None

    def test_objects_forgotten_after_reset(self):
        clusterer, collector = make_clusterer()
        push(clusterer, detection(0, 0, 0.0))
        clusterer.flush()
        clusterer.reset()
        collector.received.clear()
        push(clusterer, detection(100, 0, 10.0))
        clusterer.flush()
        (obj,) = collector.received
        assert obj.geometry.x == pytest.approx(100)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------



class TestSodaCitronClustererConfig:
    def test_get_config_has_all_constructor_params(self):
        assert SodaCitronClusterer(**_CUSTOM).get_config() == _CUSTOM

    def test_get_config_omits_fixed_dbstream_params(self):
        cfg = SodaCitronClusterer().get_config()
        assert "fading_factor" not in cfg
        assert "cleanup_interval" not in cfg

    def test_config_round_trip(self):
        cfg = SodaCitronClusterer(**_CUSTOM).get_config()
        assert SodaCitronClusterer(**cfg).get_config() == cfg

    def test_get_config_is_serializable(self):
        json.dumps(SodaCitronClusterer().get_config())

    def test_module_level_function_is_stored_as_import_path(self):
        path = SodaCitronClusterer(confidence_to_weight=paper_weight).get_config()["confidence_to_weight"]
        assert path.endswith(":paper_weight")
        assert SodaCitronClusterer(confidence_to_weight=path).confidence_to_weight is paper_weight

    def test_unimportable_function_cannot_be_stored(self, tmp_path):
        src = _UncertainSource()
        out = LocationOutput()(SodaCitronClusterer(confidence_to_weight=lambda c: c)(src))
        graph = Graph(inputs=[src], outputs=[out], crs="EPSG:32633")
        with pytest.raises(TypeError, match="cannot be stored in a graph config"):
            graph.save(str(tmp_path / "graph.json"))

    def test_registered(self):
        assert NODE_REGISTRY["SodaCitronClusterer"] is SodaCitronClusterer

    def test_graph_config_rebuilds_node(self):
        src = _UncertainSource()
        node = SodaCitronClusterer(**_CUSTOM)(src)
        out = LocationOutput()(node)
        cfg = Graph(inputs=[src], outputs=[out], crs="EPSG:32633").to_config()
        (entry,) = [n for n in cfg["nodes"] if n["type"] == "SodaCitronClusterer"]
        params = {k: v for k, v in entry.items() if k not in ("type", "name", "inputs")}
        assert NODE_REGISTRY[entry["type"]](**params).get_config() == _CUSTOM


class TestSodaCitronClustererConfigure:
    def test_raises_when_river_missing(self, spatial):
        import sys
        import unittest.mock
        clusterer = SodaCitronClusterer()
        with unittest.mock.patch.dict(sys.modules, {"river": None}):
            with pytest.raises(ImportError, match="SodaCitronClusterer.*mufasa\\[tracking\\]"):
                clusterer.configure(**spatial)

    def test_raises_when_python_ulid_missing(self, spatial):
        import sys
        import unittest.mock
        clusterer = SodaCitronClusterer()
        with unittest.mock.patch.dict(sys.modules, {"ulid": None}):
            with pytest.raises(ImportError, match="SodaCitronClusterer requires python-ulid"):
                clusterer.configure(**spatial)

    def test_configure_succeeds_when_river_installed(self, spatial):
        SodaCitronClusterer().configure(**spatial)


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

_CRS = "EPSG:32633"
_TO_WGS84 = Transformer.from_crs(_CRS, "EPSG:4326", always_xy=True)
_TO_UTM = Transformer.from_crs("EPSG:4326", _CRS, always_xy=True)


def _scenario(seed: int = 0):
    """Static objects seen by two sensors, plus low-confidence clutter.

    Five objects are detected repeatedly by both sensors and one only once, with
    high confidence. Clutter is scattered uniformly, plus a dense hotspot of
    low-confidence detections. Count-based clustering such as DBSTREAM, or
    weights that grow linearly with confidence, would miss the single sighting
    and report the hotspot as an object; the paper's weighting handles both.

    Detections are returned in WGS84 with covariances in metres, as sensors
    typically report them. Object positions are returned in UTM together with
    the IDs of each object's true detections.
    """
    rng = np.random.default_rng(seed)
    objects = [(500000.0 + 20.0 * i, 5200000.0 + 10.0 * (i % 2)) for i in range(5)]
    sensors = [(0.3, 0.9), (0.6, 0.8)]  # (position std in m, confidence)
    raw, truth = [], {}
    for k, (ox, oy) in enumerate(objects):
        truth[k] = []
        for std, conf in sensors:
            for _ in range(3):
                det_id = f"obj{k}-{len(truth[k])}"
                truth[k].append(det_id)
                raw.append((*rng.normal((ox, oy), std), conf, std ** 2, det_id))

    single = (500050.0, 5200030.0)
    objects.append(single)
    truth[len(truth)] = ["single-0"]
    raw.append((*rng.normal(single, 0.3), 0.95, 0.09, "single-0"))

    hotspot = (500080.0, 5200035.0)
    for c in range(5):
        raw.append((*rng.normal(hotspot, 0.3), 0.5, 0.09, f"hotspot-{c}"))

    for c in range(20):
        while True:
            x, y = rng.uniform(499980.0, 500120.0), rng.uniform(5199980.0, 5200040.0)
            if min(math.hypot(x - ox, y - oy) for ox, oy in objects + [hotspot]) > 5.0:
                break
        raw.append((x, y, 0.5, 1.0, f"clutter-{c}"))

    timestamps = np.sort(rng.uniform(0.0, 10.0, len(raw)))
    items = [
        UncertainObservation(
            geometry=Point(*_TO_WGS84.transform(x, y)),
            timestamp=float(t),
            confidence=conf,
            covariance=var * R,
            properties={"id": det_id},
        )
        for (x, y, conf, var, det_id), t in zip(
            (raw[i] for i in rng.permutation(len(raw))), timestamps
        )
    ]
    return items, objects, truth


def _utm(obs: Location) -> tuple[float, float]:
    return _TO_UTM.transform(obs.geometry.x, obs.geometry.y)


class TestSodaCitronClustererGraph:
    # All configurations use the paper's weighting (paper_weight, w_min = 4).
    # Each passes all end-to-end assertions for 50 scenario seeds, not only
    # the default one. Hard Mahalanobis gating misses single outlying
    # detections now and then (a chi-square gate excludes ~1 % of true ones).
    @pytest.fixture(params=[
        dict(clustering_threshold=2.5),
        dict(clustering_threshold=2.5, assignment="hard"),
        dict(clustering_threshold=2.5, assignment="soft"),
        dict(clustering_threshold=3.5, metric="mahalanobis", collapse_threshold=2.5),
        dict(clustering_threshold=3.5, metric="mahalanobis", assignment="soft"),
    ], ids=["euclidean-multi", "euclidean-hard", "euclidean-soft",
            "mahalanobis-multi", "mahalanobis-soft"])
    def pipeline(self, request):
        items, objects, truth = _scenario()
        inp = LocationInput(items)
        node = SodaCitronClusterer(
            confidence_to_weight=paper_weight, minimum_weight=4.0, **request.param
        )(inp)
        out = LocationOutput()(node)
        graph = Graph(inputs=[inp], outputs=[out], crs=_CRS)
        return graph, node, out, objects, truth

    @staticmethod
    def _run(graph, node, out) -> list[UncertainObservation]:
        graph.run()
        node.flush()  # Graph.run() does not flush nodes at end of stream
        return last_flush(out.result)

    def test_finds_every_object_and_rejects_clutter(self, pipeline):
        graph, node, out, objects, _ = pipeline
        found = self._run(graph, node, out)
        assert len(found) == len(objects)
        for obj in found:
            x, y = _utm(obj)
            assert min(math.hypot(x - ox, y - oy) for ox, oy in objects) < 1.0

    def test_associates_each_detection_with_its_object(self, pipeline):
        graph, node, out, _, truth = pipeline
        found = self._run(graph, node, out)
        associations = sorted(o.properties["members"] for o in found)
        assert associations == sorted(sorted(ids) for ids in truth.values())

    def test_rerun_after_reset_is_reproducible(self, pipeline):
        graph, node, out, _, _ = pipeline
        first = self._run(graph, node, out)
        graph.reset()
        second = self._run(graph, node, out)

        def summary(objs):
            return sorted(
                (round(o.geometry.x, 9), round(o.geometry.y, 9), o.properties["weight"],
                 tuple(sorted(o.properties["members"])))
                for o in objs
            )

        assert summary(first) == summary(second)
