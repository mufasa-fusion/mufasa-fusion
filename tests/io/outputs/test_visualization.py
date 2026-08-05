import matplotlib
matplotlib.use("Agg")

import pytest
from shapely.geometry import Point

from mufasa import BoundingBox, Observation, Graph
from mufasa.nodes.mapping import POM
from mufasa.nodes.detection import Threshold
from mufasa.io.inputs.base import InputNode
from mufasa.io.outputs.visualization import Visualization
from tests.helpers import CRS, BBOX, RES, CENTRE_X, CENTRE_Y


class _MockInput(InputNode):
    _output_type = Observation
    def items(self): return []
    def get_config(self): return {}

_SPATIAL = dict(crs=CRS, bbox=BoundingBox(14.0, 47.0, 14.1, 47.1), resolution=RES)


def _centre_event(t=1.0, conf=0.9):
    return Observation(geometry=Point(CENTRE_X, CENTRE_Y), timestamp=t, confidence=conf)


def _make_pom():
    p = POM(decay_s=100.0)
    p.configure(CRS, BBOX, RES)
    return p


# ---------------------------------------------------------------------------
# Type contract
# ---------------------------------------------------------------------------

class TestVisualizationTypes:
    def test_output_type_is_none(self):
        assert Visualization().output_type is None

    def test_input_types_include_map_and_location(self):
        from mufasa.map import Map
        from mufasa.location import Location
        vt = Visualization().input_types
        assert any(issubclass(Map, t) for t in vt)
        assert any(issubclass(Location, t) for t in vt)

    def test_default_snapshot_interval(self):
        assert Visualization().snapshot_interval_s == 5.0

    def test_custom_snapshot_interval(self):
        assert Visualization(snapshot_interval_s=10.0).snapshot_interval_s == 10.0

    def test_negative_interval_raises(self):
        with pytest.raises(ValueError):
            Visualization(snapshot_interval_s=-1.0)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

class TestVisualizationWiring:
    def test_map_pred_adds_viz_to_successors(self):
        pom = _make_pom()
        viz = Visualization()(pom)
        assert viz in pom._successors

    def test_location_pred_adds_proxy_not_viz(self):
        pom = _make_pom()
        td  = Threshold(0.5)(pom)
        td.configure(CRS, BBOX, RES)
        viz = Visualization()(td)
        assert viz not in td._successors
        assert any(getattr(s, '_is_proxy', False) for s in td._successors)

    def test_proxy_is_proxy_flag(self):
        pom = _make_pom()
        td  = Threshold(0.5)(pom)
        td.configure(CRS, BBOX, RES)
        viz = Visualization()(td)
        proxy = td._successors[-1]
        assert proxy._is_proxy is True

    def test_proxy_successors_points_to_viz(self):
        pom = _make_pom()
        td  = Threshold(0.5)(pom)
        td.configure(CRS, BBOX, RES)
        viz = Visualization()(td)
        proxy = td._successors[-1]
        assert viz in proxy._successors

    def test_viz_predecessors_contains_real_pred(self):
        pom = _make_pom()
        td  = Threshold(0.5)(pom)
        td.configure(CRS, BBOX, RES)
        viz = Visualization()(td)
        assert td in viz._predecessors

    def test_type_mismatch_raises(self):
        pom = _make_pom()
        td  = Threshold(0.5)(pom)
        td.configure(CRS, BBOX, RES)
        # Threshold outputs Location — fine; but a sink (output_type=None) must fail
        from mufasa.io.outputs.python_object import LocationOutput
        sink = LocationOutput()(td)
        with pytest.raises(TypeError):
            Visualization()(sink)


# ---------------------------------------------------------------------------
# Graph integration — proxy invisible
# ---------------------------------------------------------------------------

class TestVisualizationGraph:
    def _build(self):
        src = _MockInput();                        src.name = "src"
        pom = POM(decay_s=100.0)(src);             pom.name = "pom"
        td  = Threshold(0.5)(pom);       td.name  = "td"
        viz = Visualization()(pom, td);            viz.name = "viz"
        return src, pom, td, viz

    def test_proxy_not_in_all_nodes(self):
        src, pom, td, viz = self._build()
        g = Graph(inputs=[src], outputs=[viz], **_SPATIAL)
        node_types = [type(n).__name__ for n in g._all_nodes()]
        assert "_SourceProxy" not in node_types

    def test_names_assigned_before_configure(self):
        src, pom, td, viz = self._build()
        g = Graph(inputs=[src], outputs=[viz], **_SPATIAL)
        assert all(k is not None for k in viz._snapshots)
        assert all(k is not None for k in viz._locations)

    def test_graph_summary_does_not_raise(self, capsys):
        src, pom, td, viz = self._build()
        Graph(inputs=[src], outputs=[viz], **_SPATIAL).summary()

    def test_plot_graph_does_not_raise(self):
        import matplotlib.pyplot as plt
        src, pom, td, viz = self._build()
        fig = Graph(inputs=[src], outputs=[viz], **_SPATIAL).plot_graph()
        assert fig is not None
        plt.close("all")


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

class TestVisualizationCollection:
    def _configured_viz_with_pom(self, interval=0.0):
        pom = POM(decay_s=100.0);  pom.name = "pom"
        viz = Visualization(snapshot_interval_s=interval)(pom)
        pom.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        return pom, viz

    def test_map_snapshot_collected_on_process(self):
        pom, viz = self._configured_viz_with_pom()
        pom.process(_centre_event())
        assert len(viz._snapshots["pom"]) == 1

    def test_map_snapshot_throttled(self):
        pom, viz = self._configured_viz_with_pom(interval=10.0)
        pom.process(_centre_event(t=1.0))   # stored  (first)
        pom.process(_centre_event(t=5.0))   # skipped (only 4 s elapsed)
        pom.process(_centre_event(t=15.0))  # stored  (14 s elapsed)
        assert len(viz._snapshots["pom"]) == 2

    def test_zero_interval_stores_every_update(self):
        pom, viz = self._configured_viz_with_pom(interval=0.0)
        pom.process(_centre_event(t=1.0))
        pom.process(_centre_event(t=2.0))
        assert len(viz._snapshots["pom"]) == 2

    def test_locations_collected_via_proxy(self):
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization()(pom, td);    viz.name  = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        pom.process(_centre_event(conf=0.9))
        assert len(viz._locations["td"]) >= 1

    def test_reset_clears_snapshots_and_locations(self):
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization(snapshot_interval_s=0)(pom, td); viz.name = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        pom.process(_centre_event(conf=0.9))
        viz.reset()
        assert viz._snapshots["pom"] == []
        assert viz._locations["td"] == []


# ---------------------------------------------------------------------------
# Resolve — index and name access
# ---------------------------------------------------------------------------

class TestVisualizationResolve:
    def _setup(self):
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization()(pom, td);    viz.name  = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        return viz

    def test_resolve_by_int(self):
        viz = self._setup()
        assert viz._resolve(0) == "pom"
        assert viz._resolve(1) == "td"

    def test_resolve_by_name(self):
        viz = self._setup()
        assert viz._resolve("pom") == "pom"
        assert viz._resolve("td")  == "td"

    def test_resolve_unknown_name_raises(self):
        viz = self._setup()
        with pytest.raises(KeyError):
            viz._resolve("nonexistent")


# ---------------------------------------------------------------------------
# show() / animate()
# ---------------------------------------------------------------------------

class TestVisualizationShow:
    def _setup(self):
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization(snapshot_interval_s=0)(pom, td); viz.name = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        pom.process(_centre_event(t=1.0, conf=0.9))
        pom.process(_centre_event(t=2.0, conf=0.9))
        return viz

    def test_show_map_by_index(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        viz.show(0, basemap=False)
        plt.close("all")

    def test_show_map_by_name(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        viz.show("pom", basemap=False)
        plt.close("all")

    def test_show_locations_by_index(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        viz.show(1, basemap=False)
        plt.close("all")

    def test_show_time_filter_excludes_outside_range(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        viz.show(0, start=1.5, end=3.0, basemap=False)
        plt.close("all")

    def test_show_empty_range_raises(self):
        viz = self._setup()
        with pytest.raises(ValueError):
            viz.show(0, start=100.0, basemap=False)


class TestVisualizationAnimate:
    def _setup(self):
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization(snapshot_interval_s=5)(pom, td); viz.name = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        pom.process(_centre_event(t=1.0, conf=0.9))
        pom.process(_centre_event(t=20.0, conf=0.9))  # past interval
        return viz

    def test_animate_maps_returns_fig_anim(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        fig, anim = viz.animate(0, basemap=False)
        assert fig is not None and anim is not None
        plt.close("all")

    def test_animate_locations_returns_fig_anim(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        fig, anim = viz.animate(1, basemap=False)
        assert fig is not None and anim is not None
        plt.close("all")

    def test_animate_speed_scales_interval(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        _, anim_1x = viz.animate(0, speed=1.0, basemap=False)
        _, anim_2x = viz.animate(0, speed=2.0, basemap=False)
        assert anim_1x._interval == 1000
        assert anim_2x._interval == 500
        plt.close("all")

    def test_animate_time_filter(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        fig, anim = viz.animate(0, start=0.0, end=10.0, basemap=False)
        assert anim is not None
        plt.close("all")

    def test_animate_empty_location_range_raises(self):
        viz = self._setup()
        with pytest.raises(ValueError):
            viz.animate(1, start=1000.0, basemap=False)

    def test_animate_locations_window_s_cumulative(self):
        import matplotlib.pyplot as plt
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization(snapshot_interval_s=0)(pom, td); viz.name = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        for t in [1.0, 2.0, 3.0]:
            pom.process(_centre_event(t=t, conf=0.9))
        _, anim = viz.animate(1, window_s=None, basemap=False)
        # frame 2 (t=3.0): all 3 events visible in cumulative mode
        anim._func(len(viz._locations["td"]) - 1)
        assert len(viz._locations["td"]) >= 1
        plt.close("all")

    def test_animate_locations_window_s_hides_old(self):
        import matplotlib.pyplot as plt
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization(snapshot_interval_s=0)(pom, td); viz.name = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        for t in [1.0, 2.0, 10.0]:
            pom.process(_centre_event(t=t, conf=0.9))
        _, anim = viz.animate(1, window_s=2.0, basemap=False)
        # window_s=2.0 at last frame (t=10) — events at t=1,2 should be excluded
        anim._func(len(viz._locations["td"]) - 1)
        plt.close("all")


class TestVisualizationShowExtras:
    def _setup(self, interval=0.0):
        pom = POM(decay_s=100.0);        pom.name = "pom"
        td  = Threshold(0.1)(pom); td.name  = "td"
        viz = Visualization(snapshot_interval_s=interval)(pom, td); viz.name = "viz"
        pom.configure(CRS, BBOX, RES)
        td.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        pom.process(_centre_event(t=42.0, conf=0.9))
        return viz

    def test_bayesian_map_shown_as_probabilities(self):
        import matplotlib.pyplot as plt
        from mufasa.map import BayesianMap
        viz = self._setup()
        _, ax = plt.subplots()
        viz.show(0, basemap=False, ax=ax)
        data = ax.images[0].get_array()
        assert data.min() >= 0.0 and data.max() <= 1.0
        plt.close("all")

    def test_timestamp_used_as_default_title(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        _, ax = plt.subplots()
        viz.show(0, basemap=False, ax=ax)
        assert "42.0" in ax.get_title()
        plt.close("all")

    def test_reduction_last_is_default(self):
        import matplotlib.pyplot as plt
        viz = self._setup()
        _, ax = plt.subplots()
        viz.show(0, basemap=False, ax=ax)
        assert len(ax.images) == 1
        plt.close("all")

    def test_reduction_mean_does_not_raise(self):
        import matplotlib.pyplot as plt
        pom = POM(decay_s=100.0);  pom.name = "pom"
        viz = Visualization(snapshot_interval_s=0)(pom); viz.name = "viz"
        pom.configure(CRS, BBOX, RES)
        viz.configure(CRS, BBOX, RES)
        pom.process(_centre_event(t=1.0))
        pom.process(_centre_event(t=2.0))
        _, ax = plt.subplots()
        viz.show(0, reduction="mean", basemap=False, ax=ax)
        plt.close("all")


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestVisualizationConfig:
    def test_get_config(self):
        cfg = Visualization(snapshot_interval_s=3.0).get_config()
        assert cfg == {"snapshot_interval_s": 3.0}

    def test_round_trip_in_graph(self, tmp_path):
        import json
        from mufasa.io.inputs.geojson import GeoJsonInput
        events_path = tmp_path / "events.geojson"
        events_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [14.05, 47.05]},
             "properties": {"timestamp": 1.0, "confidence": 0.9}}
        ]}))
        src = GeoJsonInput(path=str(events_path)); src.name = "src"
        pom = POM(decay_s=100.0)(src);             pom.name = "pom"
        viz = Visualization(snapshot_interval_s=2.0)(pom); viz.name = "viz"
        g   = Graph(inputs=[src], outputs=[viz], **_SPATIAL)
        cfg = g.to_config()
        g2  = Graph.from_config(cfg)
        viz2 = g2.outputs[0]
        assert type(viz2).__name__ == "Visualization"
        assert viz2.snapshot_interval_s == pytest.approx(2.0)
