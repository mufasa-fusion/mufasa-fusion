"""Visualization output node with integrated rendering helpers."""
from __future__ import annotations

import numpy as np

from mufasa.location import Location
from mufasa.map import Map
from mufasa.io.outputs.base import OutputNode


# ---------------------------------------------------------------------------
# Private rendering helpers
# ---------------------------------------------------------------------------

def _crs_to_string(crs) -> str | None:
    if isinstance(crs, str):
        return crs
    return crs.to_string() if crs else None


def _apply_latlon_ticks(ax, crs) -> None:
    from pyproj import Transformer
    t = Transformer.from_crs(_crs_to_string(crs), "EPSG:4326", always_xy=True)
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    xmid = (xlim[0] + xlim[1]) / 2
    ymid = (ylim[0] + ylim[1]) / 2
    xticks = [x for x in ax.get_xticks() if xlim[0] <= x <= xlim[1]]
    lons, _ = t.transform(xticks, [ymid] * len(xticks))
    ax.set_xticks(xticks)
    ax.set_xticklabels([f"{lon:.4f}°" for lon in lons], rotation=30, ha="right")
    yticks = [y for y in ax.get_yticks() if ylim[0] <= y <= ylim[1]]
    _, lats = t.transform([xmid] * len(yticks), yticks)
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{lat:.4f}°" for lat in lats])


def _add_basemap(ax, crs) -> None:
    import contextily as ctx
    ctx.add_basemap(ax, crs=_crs_to_string(crs), source=ctx.providers.OpenStreetMap.Mapnik)


_REDUCTIONS = {
    "last":  lambda arrays: arrays[-1],
    "first": lambda arrays: arrays[0],
    "mean":  lambda arrays: np.mean(np.stack(arrays), axis=0),
    "min":   lambda arrays: np.minimum.reduce(arrays),
    "max":   lambda arrays: np.maximum.reduce(arrays),
}


def _plot_map(
    maps: list,
    *,
    ax=None,
    reduction: str = "last",
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    colorbar: bool = True,
    title: str | None = None,
    basemap: bool = False,
    latlon_labels: bool = False,
) -> None:
    import matplotlib.pyplot as plt
    from mufasa.map import BayesianMap

    if ax is None:
        _, ax = plt.subplots()
    if reduction not in _REDUCTIONS:
        raise ValueError(f"reduction must be one of {list(_REDUCTIONS)}; got {reduction!r}")

    arrays = [m.probabilities if isinstance(m, BayesianMap) else m.data for m in maps]
    data = _REDUCTIONS[reduction](arrays)
    ref  = maps[-1]

    bb = ref.bbox
    im = ax.imshow(
        data,
        extent=[bb.min_x, bb.max_x, bb.min_y, bb.max_y],
        origin="upper", cmap=cmap, vmin=vmin, vmax=vmax,
        aspect="equal", alpha=0.6 if basemap else 1.0, zorder=1,
    )
    if basemap:
        _add_basemap(ax, ref.crs)
    if colorbar:
        ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    if title is None:
        if len(maps) > 1:
            title = f"{reduction} over {len(maps)} snapshots"
        elif ref.timestamp:
            title = f"t = {ref.timestamp:.1f} s"
    if title:
        ax.set_title(title)
    if latlon_labels:
        _apply_latlon_ticks(ax, ref.crs)


def _animate_maps(
    maps: list,
    *,
    cmap: str = "viridis",
    interval_ms: int = 300,
    basemap: bool = False,
    latlon_labels: bool = False,
):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from mufasa.map import BayesianMap

    fig, ax = plt.subplots()
    arrays = [m.probabilities if isinstance(m, BayesianMap) else m.data for m in maps]
    vmin = float(min(a.min() for a in arrays))
    vmax = float(max(a.max() for a in arrays))
    bb = maps[0].bbox
    im = ax.imshow(
        arrays[0],
        extent=[bb.min_x, bb.max_x, bb.min_y, bb.max_y],
        origin="upper", cmap=cmap, vmin=vmin, vmax=vmax,
        aspect="equal", alpha=0.6 if basemap else 1.0, zorder=1,
    )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    title_obj = ax.set_title("")
    if basemap:
        _add_basemap(ax, maps[0].crs)
    if latlon_labels:
        _apply_latlon_ticks(ax, maps[0].crs)

    def _update(i):
        im.set_data(arrays[i])
        ts = maps[i].timestamp
        title_obj.set_text(f"t = {ts:.1f} s" if ts else f"frame {i}")
        return im, title_obj

    anim = FuncAnimation(fig, _update, frames=len(maps), interval=interval_ms, blit=False)
    return fig, anim


def _plot_locations(
    events: list,
    *,
    ax=None,
    crs=None,
    bbox=None,
    color: str = "crimson",
    markersize: float = 6,
    title: str | None = None,
    basemap: bool = False,
    latlon_labels: bool = False,
) -> None:
    import matplotlib.pyplot as plt
    import geopandas as gpd

    if ax is None:
        _, ax = plt.subplots()
    if bbox is not None:
        ax.set_xlim(bbox.min_x, bbox.max_x)
        ax.set_ylim(bbox.min_y, bbox.max_y)
    if events:
        gdf = gpd.GeoDataFrame(geometry=[e.geometry for e in events])
        if crs is not None:
            gdf = gdf.set_crs(_crs_to_string(crs))
        gdf.plot(ax=ax, color=color, markersize=markersize)
        if bbox is not None:
            ax.set_xlim(bbox.min_x, bbox.max_x)
            ax.set_ylim(bbox.min_y, bbox.max_y)
    if basemap and crs is not None:
        _add_basemap(ax, crs)
    if latlon_labels and crs is not None:
        _apply_latlon_ticks(ax, crs)
    if title:
        ax.set_title(title)


def _animate_locations(
    events: list,
    *,
    crs=None,
    bbox=None,
    window_s: float | None = None,
    color: str = "crimson",
    markersize: float = 6,
    interval_ms: int = 300,
    basemap: bool = False,
    latlon_labels: bool = False,
):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    import geopandas as gpd

    timestamped = sorted(events, key=lambda e: e.timestamp)
    if not timestamped:
        raise ValueError("animate requires at least one location")

    fig, ax = plt.subplots()
    if bbox is not None:
        xlim = (bbox.min_x, bbox.max_x)
        ylim = (bbox.min_y, bbox.max_y)
    else:
        all_gdf = gpd.GeoDataFrame(geometry=[e.geometry for e in timestamped])
        minx, miny, maxx, maxy = all_gdf.total_bounds
        px = max((maxx - minx) * 0.05, 1.0)
        py = max((maxy - miny) * 0.05, 1.0)
        xlim = (minx - px, maxx + px)
        ylim = (miny - py, maxy + py)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    if basemap and crs is not None:
        _add_basemap(ax, crs)
    if latlon_labels and crs is not None:
        _apply_latlon_ticks(ax, crs)
    title_obj = ax.set_title("")
    crs_str = _crs_to_string(crs) if crs is not None else None

    def _update(i):
        for coll in list(ax.collections):
            coll.remove()
        for patch in list(ax.patches):
            patch.remove()
        for line in list(ax.lines):
            line.remove()
        t = timestamped[i].timestamp
        if window_s is None:
            visible = [e for e in timestamped if e.timestamp <= t]
        else:
            visible = [e for e in timestamped if t - window_s <= e.timestamp <= t]
        if visible:
            gdf = gpd.GeoDataFrame(geometry=[e.geometry for e in visible])
            if crs_str is not None:
                gdf = gdf.set_crs(crs_str)
            gdf.plot(ax=ax, color=color, markersize=markersize)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        title_obj.set_text(f"t = {t:.1f} s")
        return []

    anim = FuncAnimation(fig, _update, frames=len(timestamped), interval=interval_ms, blit=False)
    return fig, anim


# ---------------------------------------------------------------------------
# _SourceProxy
# ---------------------------------------------------------------------------

class _SourceProxy:
    """Routes Location-predecessor process() calls to Visualization with source identity."""
    _is_proxy = True

    def __init__(self, viz: "Visualization", source) -> None:
        self._predecessors = [source]
        self._successors   = [viz]
        self._viz    = viz
        self._source = source
        self.name    = None

    def process(self, loc=None) -> None:
        self._viz._receive(self._source, loc)


# ---------------------------------------------------------------------------
# Visualization output node
# ---------------------------------------------------------------------------

class Visualization(OutputNode):
    """Output node that collects Map snapshots and Locations for inspection.

    Wire any number of Map or Location predecessors; access each by index or
    name after the run::

        viz = Visualization(snapshot_interval_s=5)(pom_a, pom_b, threshold)
        viz.show(0)                        # pom_a — latest snapshot
        viz.show("threshold", end=100.0)   # threshold locations up to t=100
        viz.animate(1, speed=2.0)          # pom_b at 2× real-time

    ``snapshot_interval_s`` throttles how often Map state is captured.
    Locations are always stored without throttling.

    Both ``show()`` and ``animate()`` default to ``basemap=True`` and
    ``latlon_labels=True`` and fix the axis extent to the pipeline bounding
    box.  Pass ``basemap=False`` to suppress tile fetching (e.g. in tests).
    """

    _input_types = [Map, Location]
    _output_type = None

    def __init__(self, snapshot_interval_s: float = 5.0) -> None:
        super().__init__()
        if snapshot_interval_s < 0:
            raise ValueError("snapshot_interval_s must be >= 0")
        self.snapshot_interval_s = snapshot_interval_s
        self._crs  = None
        self._bbox = None
        self._snapshots:          dict[str, list] = {}
        self._locations:          dict[str, list] = {}
        self._last_snapshot_time: dict[str, float | None] = {}

    # ------------------------------------------------------------------
    # Wiring — insert proxies for Location predecessors
    # ------------------------------------------------------------------

    def __call__(self, *inputs) -> "Visualization":
        for inp in inputs:
            if inp.output_type is None:
                raise TypeError(
                    f"{type(inp).__name__} has no output type and cannot be used as input"
                )
            if not any(issubclass(inp.output_type, t) for t in self.input_types):
                raise TypeError(
                    f"{type(inp).__name__} outputs {inp.output_type.__name__} "
                    f"but {type(self).__name__} accepts "
                    f"{[t.__name__ for t in self.input_types]}"
                )
            self._predecessors.append(inp)
            if issubclass(inp.output_type, Map):
                inp._successors.append(self)
            else:
                proxy = _SourceProxy(self, inp)
                inp._successors.append(proxy)
        return self

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def configure(self, crs, bbox, resolution) -> None:
        self._crs  = crs
        self._bbox = bbox
        self._snapshots.clear()
        self._locations.clear()
        self._last_snapshot_time.clear()
        for pred in self._predecessors:
            name = pred.name
            if issubclass(pred.output_type, Map):
                self._snapshots[name] = []
                self._last_snapshot_time[name] = None
            else:
                self._locations[name] = []

    def process(self) -> None:
        for pred in self._predecessors:
            if not issubclass(pred.output_type, Map):
                continue
            name = pred.name
            now  = pred.map.timestamp
            last = self._last_snapshot_time[name]
            if last is not None and now - last < self.snapshot_interval_s:
                continue
            self._snapshots[name].append(pred.map.copy())
            self._last_snapshot_time[name] = now

    def _receive(self, source, loc) -> None:
        self._locations[source.name].append(loc)

    def reset(self) -> None:
        for lst in self._snapshots.values():
            lst.clear()
        for lst in self._locations.values():
            lst.clear()
        for key in self._last_snapshot_time:
            self._last_snapshot_time[key] = None

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def _resolve(self, index: int | str) -> str:
        if isinstance(index, int):
            return self._predecessors[index].name
        if index in self._snapshots or index in self._locations:
            return index
        available = list(self._snapshots) + list(self._locations)
        raise KeyError(f"No predecessor named {index!r}. Available: {available}")

    def _filter_maps(self, maps: list, start, end) -> list:
        if start is not None:
            maps = [m for m in maps if m.timestamp >= start]
        if end is not None:
            maps = [m for m in maps if m.timestamp <= end]
        return maps

    def _filter_locations(self, events: list, start, end) -> list:
        if start is not None:
            events = [e for e in events if e.timestamp >= start]
        if end is not None:
            events = [e for e in events if e.timestamp <= end]
        return events

    def show(
        self,
        index: int | str,
        *,
        start:         float | None = None,
        end:           float | None = None,
        reduction:     str          = "last",
        basemap:       bool         = True,
        latlon_labels: bool         = True,
        **kwargs,
    ) -> None:
        """Render the state of a predecessor, optionally filtered to a time window."""
        name = self._resolve(index)
        if name in self._snapshots:
            maps = self._filter_maps(self._snapshots[name], start, end)
            if not maps:
                raise ValueError(f"No snapshots for '{name}' in the given time range")
            _plot_map(
                maps, reduction=reduction,
                basemap=basemap, latlon_labels=latlon_labels, **kwargs,
            )
        else:
            events = self._filter_locations(self._locations[name], start, end)
            _plot_locations(
                events, crs=self._crs, bbox=self._bbox,
                basemap=basemap, latlon_labels=latlon_labels, **kwargs,
            )

    def animate(
        self,
        index: int | str,
        *,
        start:         float | None = None,
        end:           float | None = None,
        speed:         float        = 1.0,
        basemap:       bool         = True,
        latlon_labels: bool         = True,
        **kwargs,
    ):
        """Animate snapshots or locations for a predecessor.

        Returns (fig, anim) — keep a reference to anim to prevent garbage
        collection.  ``speed`` scales playback: 1.0 = real-time, 2.0 = 2× faster.
        """
        name        = self._resolve(index)
        interval_ms = int(1000 / speed)
        if name in self._snapshots:
            maps = self._filter_maps(self._snapshots[name], start, end)
            if not maps:
                raise ValueError(f"No snapshots for '{name}' in the given time range")
            return _animate_maps(
                maps, interval_ms=interval_ms,
                basemap=basemap, latlon_labels=latlon_labels, **kwargs,
            )
        else:
            events = self._filter_locations(self._locations[name], start, end)
            if not events:
                raise ValueError(f"No locations for '{name}' in the given time range")
            return _animate_locations(
                events, crs=self._crs, bbox=self._bbox,
                interval_ms=interval_ms,
                basemap=basemap, latlon_labels=latlon_labels, **kwargs,
            )

    def get_config(self) -> dict:
        return {"snapshot_interval_s": self.snapshot_interval_s}
