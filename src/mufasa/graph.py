import json
import warnings
from collections import deque

from pyproj import Transformer

from mufasa import BoundingBox, Map
from mufasa import Node


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _project_bbox(bbox: BoundingBox, crs: str) -> BoundingBox:
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    min_x, min_y = transformer.transform(bbox.min_x, bbox.min_y)
    max_x, max_y = transformer.transform(bbox.max_x, bbox.max_y)
    return BoundingBox(min_x, min_y, max_x, max_y)


def _suggest_utm_crs(bbox: BoundingBox) -> str | None:
    """Return a UTM EPSG string derived from bbox centre, or None if bbox
    does not look like WGS84 degree coordinates."""
    if not (
        -180 <= bbox.min_x <= 180 and -180 <= bbox.max_x <= 180
        and -90 <= bbox.min_y <= 90 and -90 <= bbox.max_y <= 90
    ):
        return None
    lon = (bbox.min_x + bbox.max_x) / 2
    lat = (bbox.min_y + bbox.max_y) / 2
    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def _reachable_from(inputs: list[Node]) -> set[Node]:
    """DFS from inputs; raises ValueError on cycle; returns reachable non-proxy nodes."""
    visited:  set[int]  = set()
    on_stack: set[int]  = set()
    reachable: set[Node] = set()

    def dfs(node: Node) -> None:
        visited.add(id(node))
        on_stack.add(id(node))
        if not getattr(node, '_is_proxy', False):
            reachable.add(node)
        for succ in node._successors:
            if id(succ) not in visited:
                dfs(succ)
            elif id(succ) in on_stack:
                raise ValueError(
                    f"Cycle detected in pipeline involving {type(succ).__name__}"
                )
        on_stack.remove(id(node))

    for node in inputs:
        if id(node) not in visited:
            dfs(node)

    return reachable


def _real_successors(node) -> list:
    """Successors of node, unwrapping proxy objects transparently."""
    return [
        real
        for succ in node._successors
        for real in (succ._successors if getattr(succ, '_is_proxy', False) else [succ])
    ]


def _assign_names(nodes: list[Node]) -> None:
    """Auto-assign names to unnamed nodes, then validate uniqueness."""
    type_counts: dict[str, int] = {}
    for node in nodes:
        if node.name is None:
            key = type(node).__name__.lower()
            idx = type_counts.get(key, 0)
            type_counts[key] = idx + 1
            node.name = f"{key}_{idx}"

    seen: set[str] = set()
    for node in nodes:
        if node.name in seen:
            raise ValueError(
                f"Duplicate node name '{node.name}'. "
                "Assign unique names to all nodes."
            )
        seen.add(node.name)


def _node_depths(nodes: list[Node]) -> dict:
    """Return the display depth (longest path from any input) for each node.

    Uses iterative relaxation so depths are correct regardless of visitation
    order.  Source nodes (no predecessors) are placed one step before their
    earliest successor to avoid backward-looking arrows for static inputs.
    """
    node_set = set(nodes)
    result   = {node: 0 for node in nodes}

    changed = True
    while changed:
        changed = False
        for node in nodes:
            for real_succ in _real_successors(node):
                if real_succ in node_set:
                    new_d = result[node] + 1
                    if new_d > result[real_succ]:
                        result[real_succ] = new_d
                        changed = True

    for node in nodes:
        if not node._predecessors and node._successors:
            succs = [s for s in _real_successors(node) if s in node_set]
            if succs:
                result[node] = min(result[s] for s in succs) - 1

    return result


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

class Graph:
    def __init__(
        self,
        inputs:     list[Node],
        outputs:    list[Node],
        *,
        crs:        str | None = None,
        bbox:       BoundingBox | None = None,
        resolution: tuple[float, float] | None = None,
    ) -> None:
        self.inputs      = inputs
        self.outputs     = outputs
        self.crs         = crs
        self.bbox_wgs84  = bbox
        self.bbox        = _project_bbox(bbox, crs) if bbox is not None and crs is not None else bbox
        self.resolution  = resolution
        self._validate()
        _assign_names(self.nodes)
        for node in self.nodes:
            node.configure(crs, self.bbox, resolution)
        self._configure_run()

    def _all_nodes(self) -> list[Node]:
        """Return all nodes in the pipeline in topological order (Kahn's algorithm).

        Discovers nodes via forward BFS from inputs and backward BFS from outputs,
        then produces a stable topological ordering (predecessors before successors).
        Proxy objects are excluded.
        """
        seen: set[int] = set()
        all_nodes: list[Node] = []

        queue = deque(self.inputs)
        while queue:
            node = queue.popleft()
            if id(node) in seen:
                continue
            seen.add(id(node))
            if not getattr(node, '_is_proxy', False):
                all_nodes.append(node)
            queue.extend(node._successors)

        back_seen: set[int] = set()
        queue = deque(self.outputs)
        while queue:
            node = queue.popleft()
            if id(node) in back_seen:
                continue
            back_seen.add(id(node))
            if id(node) not in seen:
                seen.add(id(node))
                if not getattr(node, '_is_proxy', False):
                    all_nodes.append(node)
            queue.extend(node._predecessors)

        node_set = {id(n) for n in all_nodes}

        in_degree: dict[int, int] = {id(n): 0 for n in all_nodes}
        for node in all_nodes:
            for succ in node._successors:
                if id(succ) in node_set and not getattr(succ, '_is_proxy', False):
                    in_degree[id(succ)] += 1

        queue = deque(n for n in all_nodes if in_degree[id(n)] == 0)
        result: list[Node] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for succ in node._successors:
                if id(succ) in node_set and not getattr(succ, '_is_proxy', False):
                    in_degree[id(succ)] -= 1
                    if in_degree[id(succ)] == 0:
                        queue.append(succ)

        return result

    def _validate(self) -> None:
        from mufasa.io.inputs.base import InputNode
        if not all(isinstance(n, InputNode) for n in self.inputs):
            bad = [type(n).__name__ for n in self.inputs if not isinstance(n, InputNode)]
            raise ValueError(f"Graph inputs must be InputNode subclasses; got: {', '.join(bad)}")

        if self.crs is None:
            suggestion = _suggest_utm_crs(self.bbox) if self.bbox is not None else None
            if suggestion:
                msg = (
                    f"No CRS specified. The bounding box coordinates look like WGS84 "
                    f"degrees — {suggestion} may be an appropriate UTM projection. "
                    "Without a CRS, spatial operations will treat the raw coordinate "
                    "values as metres, which will produce incorrect distances and "
                    "unexpected behaviour. Pass crs=<EPSG string> to Graph() to fix this."
                )
            else:
                msg = (
                    "No CRS specified. Ensure all input data is already in a "
                    "Cartesian coordinate system with units of metres (e.g. a UTM "
                    "projection). Using geographic coordinates (WGS84 degrees) will "
                    "produce incorrect distances and unexpected behaviour."
                )
            warnings.warn(msg, stacklevel=3)

        self.nodes: list[Node] = self._all_nodes()
        
        output_set = set(self.outputs)
        input_set  = set(self.inputs)
        reachable  = _reachable_from(self.inputs)

        # Check if all outputs are reached
        for node in self.outputs:
            if node not in reachable:
                raise ValueError(
                    f"{type(node).__name__} output is not reachable from any input"
                )

        # Check if all output nodes are declared
        for node in reachable:
            if not node._successors and node not in output_set:
                raise ValueError(
                    f"{type(node).__name__} has no successors but is not declared as an output"
                )

        # Check if all input nodes are declared
        for node in self.nodes:
            if isinstance(node, InputNode) and not node._predecessors and node not in input_set:
                raise ValueError(
                    f"{type(node).__name__} has no predecessors but is not declared as an input"
                )

        # Check if BBOX and CRS are defined if Graph handles Map nodes
        missing   = [name for name, val in
                     [("bbox", self.bbox), ("resolution", self.resolution)] if val is None]
        map_nodes = [type(n).__name__ for n in self.nodes
                     if (n.output_type is not None and issubclass(n.output_type, Map))
                     or any(issubclass(t, Map) for t in n.input_types)]
        if missing and map_nodes:
            raise ValueError(
                f"Pipeline contains nodes that handle Map data "
                f"({', '.join(map_nodes)}) but spatial parameters "
                f"{missing} are missing. Pass bbox and resolution to Graph()."
            )

        # Give a warning if the BBOX is large
        if self.bbox is not None and self.resolution is not None:
            w = (self.bbox.max_x - self.bbox.min_x) / self.resolution[0]
            h = (self.bbox.max_y - self.bbox.min_y) / self.resolution[1]
            if w * h > 1_000_000:
                warnings.warn(
                    f"BoundingBox at resolution {self.resolution} produces "
                    f"{w*h:,.0f} pixels ({w:.0f}×{h:.0f}). "
                    "Consider a coarser resolution or smaller bbox to avoid "
                    "excessive memory use.",
                    stacklevel=3,
                )

    def _configure_run(self) -> None:
        import queue as _queue_mod
        import threading
        from mufasa.io.inputs.streaming import StreamingInputNode

        file_inputs   = [n for n in self.inputs if not isinstance(n, StreamingInputNode)]
        stream_inputs = [n for n in self.inputs if isinstance(n, StreamingInputNode)]

        if file_inputs and stream_inputs:
            raise ValueError(
                "Cannot mix file and streaming inputs in the same pipeline. "
                "Use separate pipelines for file and streaming sources."
            )

        self._stream_inputs = stream_inputs

        if file_inputs:
            pairs = [(item, inp) for inp in file_inputs for item in inp.items()]
            self._file_items = sorted(pairs, key=lambda x: x[0].timestamp)
        else:
            _STOP = object()
            self._queue: _queue_mod.SimpleQueue = _queue_mod.SimpleQueue()
            self._stop_sentinel = _STOP
            self._n_stops = len(stream_inputs)
            def _worker(inp):
                for item in inp.items():
                    self._queue.put((item, inp))
                self._queue.put((_STOP, None))
            for inp in stream_inputs:
                threading.Thread(target=_worker, args=(inp,), daemon=True).start()

    def run(self) -> None:
        try:
            if self._stream_inputs:
                running = self._n_stops
                while running:
                    item, inp = self._queue.get()
                    if item is self._stop_sentinel:
                        running -= 1
                    else:
                        inp._dispatch(item)
            else:
                for item, inp in self._file_items:
                    inp._dispatch(item)
        except KeyboardInterrupt:
            pass
        finally:
            for out in self.outputs:
                out.save()

    def stop(self) -> None:
        """Signal all streaming inputs to stop."""
        for inp in self._stream_inputs:
            inp.stop()

    def reset(self) -> None:
        """Reset all nodes to their initial state.

        Call between runs to prevent state from one run affecting the next.
        """
        for node in self.nodes:
            node.reset()
        self._configure_run()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_config(self) -> dict:
        """Return the full pipeline as a plain serializable dict."""
        serialized = []
        for node in self.nodes:
            node_cfg: dict = {"type": type(node).__name__, "name": node.name}
            pred_names = [p.name for p in node._predecessors]
            if pred_names:
                node_cfg["inputs"] = pred_names
            node_cfg.update(node.get_config())
            serialized.append(node_cfg)

        return {
            "spatial": {
                "crs":        self.crs,
                "bbox":       list(self.bbox_wgs84) if self.bbox_wgs84 is not None else None,
                "resolution": list(self.resolution) if self.resolution is not None else None,
            },
            "inputs":  [n.name for n in self.inputs],
            "outputs": [n.name for n in self.outputs],
            "nodes":   serialized,
        }

    @classmethod
    def from_config(cls, config: dict) -> "Graph":
        """Reconstruct a Graph from a config dict produced by to_config()."""
        from mufasa.registry import NODE_REGISTRY

        spatial    = config.get("spatial", {})
        crs        = spatial.get("crs")
        bbox       = BoundingBox(*spatial["bbox"]) if spatial.get("bbox") is not None else None
        resolution = tuple(spatial["resolution"]) if spatial.get("resolution") is not None else None

        node_by_name: dict[str, Node] = {}
        for nc in config["nodes"]:
            nc = dict(nc)
            type_name  = nc.pop("type")
            name       = nc.pop("name")
            pred_names = nc.pop("inputs", [])

            node_cls = NODE_REGISTRY.get(type_name)
            if node_cls is None:
                raise ValueError(
                    f"Unknown node type '{type_name}'. "
                    f"Available: {sorted(NODE_REGISTRY)}"
                )

            node = node_cls(**nc)
            node.name = name
            if pred_names:
                node(*[node_by_name[n] for n in pred_names])
            node_by_name[name] = node

        inputs  = [node_by_name[n] for n in config["inputs"]]
        outputs = [node_by_name[n] for n in config["outputs"]]
        return cls(inputs=inputs, outputs=outputs, crs=crs, bbox=bbox, resolution=resolution)

    def save(self, path: str) -> None:
        """Serialize the pipeline to a JSON file."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_config(), fh, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Graph":
        """Load and reconstruct a Graph from a JSON file."""
        with open(path, encoding="utf-8") as fh:
            return cls.from_config(json.load(fh))

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def summary(self) -> None:
        """Print a human-readable description of the pipeline's nodes and connections."""
        input_set  = set(self.inputs)
        output_set = set(self.outputs)

        processing = [n for n in self.nodes if n not in output_set]
        outputs    = [n for n in self.nodes if n in output_set]
        nodes      = processing + outputs

        index = {id(n): i for i, n in enumerate(nodes)}

        W = 74
        print("═" * W)
        print("  Graph")
        print("─" * W)
        print(f"  CRS        {self.crs or '(not configured)'}")
        if self.bbox_wgs84 is not None:
            b = self.bbox_wgs84
            if self.crs is not None:
                print(f"  BBox       ({b.min_x}°, {b.min_y}°) → ({b.max_x}°, {b.max_y}°)  [WGS84]")
            else:
                print(f"  BBox       ({b.min_x}, {b.min_y}) → ({b.max_x}, {b.max_y})  [local]")
        else:
            print("  BBox       (not configured)")
        print(f"  Resolution {self.resolution} m/px" if self.resolution is not None else "  Resolution (not configured)")
        print(f"  Nodes      {len(nodes)}  "
              f"(inputs: {len(self.inputs)}, outputs: {len(self.outputs)})")
        print("═" * W)
        print(f"  {'#':<3} {'Node':<28} {'Accepts':<18} {'Produces':<12} {'Inputs'}")
        print("─" * W)

        for node in nodes:
            i     = index[id(node)]
            tags  = (["in"] if node in input_set else []) + (["out"] if node in output_set else [])
            label = node.name if node.name else type(node).__name__
            if tags:
                label += f" [{', '.join(tags)}]"

            accepts  = ", ".join(t.__name__ for t in node.input_types) or "—"
            produces = node.output_type.__name__ if node.output_type else "—"
            from_ids = ", ".join(str(index[id(p)]) for p in node._predecessors) or "—"

            print(f"  {i:<3} {label:<28} {accepts:<18} {produces:<12} {from_ids}")

        print("═" * W)

    def plot_graph(self):
        """Render the pipeline DAG as a matplotlib figure.

        Returns the Figure so the caller can display, save, or embed it.
        Input nodes are green, output nodes are red, processing nodes are blue.
        """
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt
        from collections import defaultdict

        nodes      = self.nodes
        depths     = _node_depths(nodes)
        input_set  = set(self.inputs)
        output_set = set(self.outputs)

        by_depth: dict = defaultdict(list)
        for node in nodes:
            by_depth[depths[node]].append(node)

        sorted_layers = sorted(by_depth.keys())

        def _bc(node, pos, neighbours):
            vals = [pos[nb] for nb in neighbours if nb in pos]
            return sum(vals) / len(vals) if vals else pos.get(node, 0.0)

        for _ in range(4):
            pos = {n: float(i) for d in sorted_layers for i, n in enumerate(by_depth[d])}
            for d in sorted_layers:
                by_depth[d].sort(key=lambda n: _bc(n, pos, n._predecessors))
            pos = {n: float(i) for d in sorted_layers for i, n in enumerate(by_depth[d])}
            for d in reversed(sorted_layers):
                by_depth[d].sort(key=lambda n: _bc(n, pos, n._successors))

        max_col = max(depths.values(), default=0)
        max_row = max(len(g) for g in by_depth.values())

        DX, DY = 3.0, 1.6
        BOX_W  = 2.2
        BOX_H  = 0.7

        positions: dict = {}
        for col, group in by_depth.items():
            n = len(group)
            for row, node in enumerate(group):
                positions[node] = (col * DX, -(row - (n - 1) / 2) * DY)

        fig, ax = plt.subplots(
            figsize=(max(5, (max_col + 1) * DX + BOX_W),
                     max(3, (max_row + 1) * DY))
        )
        ax.set_aspect("equal")
        ax.axis("off")

        for node in nodes:
            x0, y0 = positions[node]
            for real_succ in _real_successors(node):
                if real_succ not in positions:
                    continue
                x1, y1 = positions[real_succ]
                ax.annotate(
                    "",
                    xy=(x1 - BOX_W / 2, y1),
                    xytext=(x0 + BOX_W / 2, y0),
                    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.2),
                )

        for node, (x, y) in positions.items():
            fc = "#b7e4b7" if node in input_set else "#f4a8a8" if node in output_set else "#a8c4f4"
            ax.add_patch(mpatches.FancyBboxPatch(
                (x - BOX_W / 2, y - BOX_H / 2), BOX_W, BOX_H,
                boxstyle="round,pad=0.05",
                facecolor=fc, edgecolor="#333333", linewidth=1.0,
            ))
            ax.text(x, y, type(node).__name__, ha="center", va="center", fontsize=8)

        ax.legend(
            handles=[
                mpatches.Patch(facecolor="#b7e4b7", edgecolor="#333333", label="Input"),
                mpatches.Patch(facecolor="#a8c4f4", edgecolor="#333333", label="Processing"),
                mpatches.Patch(facecolor="#f4a8a8", edgecolor="#333333", label="Output"),
            ],
            loc="upper right", fontsize=8,
        )
        ax.autoscale_view()
        plt.tight_layout()
        return fig
