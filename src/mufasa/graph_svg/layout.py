"""Node positions: layers from top to bottom, ordered to reduce crossings, aligned with their neighbours."""

from dataclasses import dataclass
from functools import cache

from mufasa.graph_svg.spec import GraphSpec

DX = 180  # Horizontal distance between neighbouring nodes
DY = 145  # Vertical distance between layers


@dataclass
class Layout:
    nodes: dict[str, tuple[float, float]]
    # Points that edges skipping layers pass through, one per skipped layer, so they are routed around nodes there
    bends: dict[tuple[str, str], list[tuple[float, float]]]


def layout(spec: GraphSpec) -> Layout:
    depths = _depths(spec)

    # Edges that skip layers get a helper point in each skipped layer; helpers are ordered and spaced like nodes
    helpers, edges = {}, []
    for a, b in spec.edges:
        chain = [a, *(f"{a}->{b}@{d}" for d in range(depths[a] + 1, depths[b])), b]
        helpers[a, b] = chain[1:-1]
        depths.update({h: depths[a] + i for i, h in enumerate(chain[1:-1], start=1)})
        edges += zip(chain, chain[1:])

    preds, succs = _neighbours(depths, edges)
    layers = [[] for _ in range(max(depths.values()) + 1)]
    for n, depth in depths.items():
        layers[depth].append(n)
    _reduce_crossings(layers, preds, succs)
    x = _x_positions(layers, preds, succs, is_helper=lambda n: n not in spec.nodes)

    position = {n: (x[n], depths[n] * DY) for n in depths}
    return Layout({n: position[n] for n in spec.nodes}, {e: [position[h] for h in hs] for e, hs in helpers.items()})


def _neighbours(nodes, edges) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    preds = {n: [] for n in nodes}
    succs = {n: [] for n in nodes}
    for a, b in edges:
        succs[a].append(b)
        preds[b].append(a)
    return preds, succs


def _depths(spec: GraphSpec) -> dict[str, int]:
    """Each node one layer below its deepest input; sources one layer above their earliest successor."""
    preds, succs = _neighbours(spec.nodes, spec.edges)

    @cache
    def depth(n: str) -> int:
        return max((depth(p) + 1 for p in preds[n]), default=0)

    depths = {n: depth(n) for n in spec.nodes}
    for n in spec.nodes:
        if not preds[n] and succs[n]:
            depths[n] = min(depths[s] for s in succs[n]) - 1
    top = min(depths.values())
    return {n: d - top for n, d in depths.items()}


def _reduce_crossings(layers: list[list[str]], preds, succs, sweeps: int = 4) -> None:
    """Sort each layer by the average position of its neighbours (barycenter heuristic), sweeping down and up."""
    for _ in range(sweeps):
        for ordered_layers, neighbours in ((layers, preds), (layers[::-1], succs)):
            for layer in ordered_layers:
                position = {n: i for lay in layers for i, n in enumerate(lay)}
                layer.sort(key=lambda n: _mean([position[m] for m in neighbours[n]], default=position[n]))


def _x_positions(layers: list[list[str]], preds, succs, is_helper) -> dict[str, float]:
    """The widest layer is spaced evenly; layers below it are centered under their inputs, layers above it over
    their successors. Nodes stay DX apart, helper points half that."""
    def gap(a: str, b: str) -> float:
        return DX / 2 if is_helper(a) or is_helper(b) else DX

    widest = max(range(len(layers)), key=lambda d: len(layers[d]))
    x = _spread(layers[widest], {n: 0.0 for n in layers[widest]}, gap)
    below, above = range(widest + 1, len(layers)), range(widest - 1, -1, -1)
    for depth, neighbours in [*((d, preds) for d in below), *((d, succs) for d in above)]:
        fallback = max(x.values()) + DX
        desired = {n: _mean([x[m] for m in neighbours[n] if m in x], default=fallback) for n in layers[depth]}
        x.update(_spread(layers[depth], desired, gap))
    left = min(x.values())
    return {n: value - left for n, value in x.items()}


def _spread(order: list[str], desired: dict[str, float], gap) -> dict[str, float]:
    """Positions close to ``desired`` that keep ``order`` and the gaps between neighbours, centered like ``desired``."""
    xs = []
    for prev, n in zip([None, *order], order):
        xs.append(desired[n] if prev is None else max(desired[n], xs[-1] + gap(prev, n)))
    shift = _mean([desired[n] for n in order]) - _mean(xs)
    return {n: value + shift for n, value in zip(order, xs)}


def _mean(values: list[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default
