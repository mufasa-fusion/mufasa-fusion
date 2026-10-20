import copy
from collections.abc import Hashable

import numpy as np
from scipy.special import logit, expit
from river import cluster
from river.cluster.dbstream import DBSTREAMMicroCluster
from ulid import ULID


class SodaCitronMicroCluster(DBSTREAMMicroCluster):
    """SODA-CitrON Micro-cluster class"""

    def __init__(self, x=None, conf=None, cov=None, last_update=None, weight=None, id=None, members=None):
        super().__init__(x=x, last_update=last_update, weight=weight)
        self.lo_conf = logit(conf)
        self.cov = cov
        inv_cov = np.linalg.inv(cov)
        self.Y = inv_cov # information matrix
        self.y = inv_cov @ x # information vector
        self.id = id
        self.members: set[Hashable] = members

    def merge(self, cluster: 'SodaCitronMicroCluster'):
        # merge information matrix and vector
        self.Y = self.Y + cluster.Y
        self.y = self.y + cluster.y
        # compute new cluster covariance, center and confidence
        self.cov = np.linalg.inv(self.Y)
        self.center = self.cov @ self.y
        self.lo_conf += cluster.lo_conf
        # take ID of stronger cluster
        if self.weight < cluster.weight:
            self.id = cluster.id
        # merge weights
        self.weight += cluster.weight
        self.members = self.members | cluster.members

    @property
    def conf(self) -> float:
        return expit(self.lo_conf)


class SodaCitron(cluster.DBSTREAM):
    def __init__(
        self,
        # The units depend on `metric`: for "euclidean" it is a distance in the
        # data's own units; for "mahalanobis" it is a distance in standard
        # deviations, so the gate is a chi-square test with dim(x) DOF
        # (2D: 2.45 ~= 95%, 3.03 ~= 99%).
        clustering_threshold: float = 1.0,
        intersection_factor: float = 0.3,
        minimum_weight: float = 1.0,
        metric: str = "euclidean",
        use_innovation_cov: bool = True,
        collapse_threshold: float | None = None,
        # How a detection that gates to several micro-clusters is shared out:
        #   "multi" - fuse the FULL detection into every gated cluster
        #   "hard"  - fuse only into the single closest gated cluster
        #   "soft"  - split the detection across gated clusters by normalised
        #             association weights beta_i (sum = 1), conserves total
        #             fused information.
        assignment: str = "multi",
    ):
        super().__init__(clustering_threshold=clustering_threshold,
                         fading_factor=0.0,
                         cleanup_interval=1,
                         intersection_factor=intersection_factor,
                         minimum_weight=minimum_weight)
        if not (callable(metric) or metric in ("euclidean", "mahalanobis")):
            raise ValueError(
                "metric must be 'euclidean', 'mahalanobis', or a callable, "
                f"got {metric!r}"
            )
        self.metric = metric
        self.use_innovation_cov = use_innovation_cov
        if assignment not in ("multi", "hard", "soft"):
            raise ValueError(
                f"assignment must be 'multi', 'hard', or 'soft', got {assignment!r}"
            )
        self.assignment = assignment
        if collapse_threshold is not None:
            self.collapse_threshold = collapse_threshold
        elif assignment == "multi":
            self.collapse_threshold = clustering_threshold
        else:
            self.collapse_threshold = 0.0
        self._meas_cov = None  # measurement cov of the current sample, for gating
        self._clusters: dict[int, SodaCitronMicroCluster] = {}
        self._micro_clusters: dict[int, SodaCitronMicroCluster] = {}

    @staticmethod
    def _distance(point_a, point_b):
        return np.linalg.norm(point_a - point_b)

    def _mahalanobis_info(self, mc: 'SodaCitronMicroCluster') -> np.ndarray:
        if self.use_innovation_cov and self._meas_cov is not None:
            return np.linalg.inv(mc.cov + self._meas_cov)  # S^-1 = (P + R)^-1
        return mc.Y                                         # = Sigma_cluster^-1

    def _association_weights(self, x: np.ndarray, gated: dict) -> dict:
        # Return beta_i in [0, 1] for each gated cluster, controlling how much of
        # the detection is fused into it.
        #   multi -> 1.0 for every cluster
        #   hard  -> 1.0 for the single closest cluster, 0.0 for the rest
        #   soft  -> softmax over -0.5 * d^2
        # d^2 is the squared Mahalanobis distance
        if self.assignment == "multi":
            return {i: 1.0 for i in gated}

        d_sq = {}
        for i, mc in gated.items():
            delta = x - mc.center
            d_sq[i] = float(delta @ self._mahalanobis_info(mc) @ delta)

        if self.assignment == "hard":
            best = min(d_sq, key=d_sq.get)
            return {i: (1.0 if i == best else 0.0) for i in gated}

        m = min(d_sq.values())
        exps = {i: np.exp(-0.5 * (d_sq[i] - m)) for i in gated}
        z = sum(exps.values())
        return {i: e / z for i, e in exps.items()}

    def _find_fixed_radius_nn(self, x: np.ndarray):
        if self.metric == "euclidean":
            return super()._find_fixed_radius_nn(x)

        neighbor_clusters = {}
        if callable(self.metric):
            for i, mc in self._micro_clusters.items():
                if self.metric(x, mc, self._meas_cov) < self.clustering_threshold:
                    neighbor_clusters[i] = mc
            return neighbor_clusters

        gate_sq = self.clustering_threshold ** 2
        for i, mc in self._micro_clusters.items():
            delta = x - mc.center
            info = self._mahalanobis_info(mc)
            if float(delta @ info @ delta) < gate_sq:
                neighbor_clusters[i] = mc
        return neighbor_clusters

    def _update(self, x: np.ndarray, conf: float, cov: np.ndarray, w: float, sample_id: Hashable):
        self._meas_cov = cov # remember current measurement cov for Mahalanobis gating
        neighbor_clusters = self._find_fixed_radius_nn(x) # Note: to achieve log-linear complexity, implement efficiently, e.g. with r-tree

        if len(neighbor_clusters) < 1:
            # create new micro cluster
            cluster_id = ULID()
            if len(self._micro_clusters) > 0:
                self._micro_clusters[max(self._micro_clusters.keys()) + 1] = SodaCitronMicroCluster(
                    x=x, conf=conf, cov=cov, last_update=self._time_stamp, weight=w, id=cluster_id, members={sample_id}
                )
            else:
                self._micro_clusters[0] = SodaCitronMicroCluster(
                    x=x, conf=conf, cov=cov, last_update=self._time_stamp, weight=w, id=cluster_id, members={sample_id}
                )
        else:
            # update existing micro clusters
            betas = self._association_weights(x, neighbor_clusters)
            updated = [i for i in neighbor_clusters.keys() if betas[i] > 0.0]
            inv_cov = np.linalg.inv(cov)  # measurement information, same for all i

            current_centers = {}
            current_Y = {}
            current_y = {}
            current_covs = {}
            current_confs = {}
            for i in updated:
                beta = betas[i]
                current_centers[i] = self._micro_clusters[i].center
                current_Y[i] = self._micro_clusters[i].Y
                current_y[i] = self._micro_clusters[i].y
                current_covs[i] = self._micro_clusters[i].cov
                current_confs[i] = self._micro_clusters[i].lo_conf
                self._micro_clusters[i].weight = (
                    self._micro_clusters[i].weight
                    * 2
                    ** (
                        -self.fading_factor
                        * (self._time_stamp - self._micro_clusters[i].last_update)
                    )
                    + beta * w
                )

                # Fuse the (beta-scaled) measurement information into cluster i
                beta_inv_cov = beta * inv_cov
                self._micro_clusters[i].Y = self._micro_clusters[i].Y + beta_inv_cov
                self._micro_clusters[i].y = self._micro_clusters[i].y + (beta_inv_cov @ x)

                # compute new cluster covariance, center and log-odds confidence
                self._micro_clusters[i].cov = (
                    np.linalg.inv(self._micro_clusters[i].Y)
                )
                self._micro_clusters[i].center = (
                     self._micro_clusters[i].cov @ self._micro_clusters[i].y
                )
                self._micro_clusters[i].lo_conf = (
                    self._micro_clusters[i].lo_conf + beta * logit(conf)
                )

                # add to cluster members
                self._micro_clusters[i].members.add(sample_id)

                self._micro_clusters[i].last_update = self._time_stamp

                # update shared density (only between co-updated clusters)
                for j in updated:
                    if j > i:
                        try:
                            self.s[i][j] = (
                                self.s[i][j]
                                * 2 ** (-self.fading_factor * (self._time_stamp - self.s_t[i][j]))
                                + w
                            )
                            self.s_t[i][j] = self._time_stamp
                        except KeyError:
                            try:
                                self.s[i][j] = w
                                self.s_t[i][j] = self._time_stamp
                            except KeyError:
                                self.s[i] = {j: w}
                                self.s_t[i] = {j: self._time_stamp}

            # prevent collapsing clusters
            for i in updated:
                for j in updated:
                    if j > i:
                        if (
                            self._distance(
                                self._micro_clusters[i].center,
                                self._micro_clusters[j].center,
                            )
                            < self.collapse_threshold
                        ):
                            # revert states of mc_i and mc_j to previous values
                            self._micro_clusters[i].center = current_centers[i]
                            self._micro_clusters[j].center = current_centers[j]
                            self._micro_clusters[i].Y = current_Y[i]
                            self._micro_clusters[j].Y = current_Y[j]
                            self._micro_clusters[i].y = current_y[i]
                            self._micro_clusters[j].y = current_y[j]
                            self._micro_clusters[i].cov = current_covs[i]
                            self._micro_clusters[j].cov = current_covs[j]
                            self._micro_clusters[i].lo_conf = current_confs[i]
                            self._micro_clusters[j].lo_conf = current_confs[j]

        self._time_stamp += 1

    def _generate_clusters_from_labels(self, cluster_labels):
        # Group micro clusters by label in one pass, preserving the input ordering.
        by_label: dict[int, list[SodaCitronMicroCluster]] = {}
        for index, label in cluster_labels.items():
            # Only micro clusters reaching the minimum weight become objects
            # (Algorithm 2, line 19). river >= 0.24.1 already leaves lighter ones
            # unlabelled; older releases label every micro cluster.
            if label is None or self._micro_clusters[index].weight < self.minimum_weight:
                continue
            by_label.setdefault(label, []).append(self._micro_clusters[index])

        if not by_label:
            return 0, {}

        clusters: dict[int, SodaCitronMicroCluster] = {}
        for label in sorted(by_label):
            members = by_label[label]
            first = members[0]
            macro_cluster = copy.copy(first)
            macro_cluster.members = set(first.members)
            for member in members[1:]:
                macro_cluster.merge(member)
            clusters[label] = macro_cluster

        return len(clusters), clusters

    def learn_one(self, x: np.ndarray, conf: float, cov: np.ndarray, w: float=1.0, id: Hashable=None):
        self._update(x, conf, cov, w, id)

        if self.fading_factor > 0 and self._time_stamp % self.cleanup_interval == 0:
            self._cleanup()

        self.clustering_is_up_to_date = False

    def predict_one(self, x: np.ndarray, w: float=None):
        raise NotImplementedError

    @property
    def clusters(self) -> dict[int, SodaCitronMicroCluster]:
        self._recluster()
        return self._clusters

    @property
    def micro_clusters(self) -> dict[int, SodaCitronMicroCluster]:
        return self._micro_clusters
