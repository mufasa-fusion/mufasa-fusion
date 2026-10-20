"""Node positions: layers from top to bottom, ordered to reduce crossings, aligned with their neighbours."""

import math
from dataclasses import dataclass
from functools import cache

from mufasa.graph_svg.spec import GraphSpec

DX = 180  # Horizontal distance between neighbouring nodes
DY = 145  # Vertical distance between layers
TRACK = 12  # Vertical distance between parallel horizontal edge segments in the gap between two layers


@dataclass
class Layout:
    nodes: dict[str, tuple[float, float]]
    # Points that edges skipping layers pass through, one per skipped layer, so they are routed around nodes there
    bends: dict[tuple[str, str], list[tuple[float, float]]]
    # Height of the horizontal segment in each gap between layers an edge crosses, from top to bottom
    tracks: dict[tuple[str, str], list[float]]


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

    chains = {(a, b): [a, *hs, b] for (a, b), hs in helpers.items()}
    track_of, counts = _tracks(chains, x, depths)

    # Each gap between layers is as high as its tracks need; tracks are centered in it
    y = [0.0]
    for depth in range(len(layers) - 1):
        y.append(y[-1] + DY + (counts.get(depth, 1) - 1) * TRACK)

    def track_y(depth: int, track: int) -> float:
        return (y[depth] + y[depth + 1]) / 2 + (track - (counts.get(depth, 1) - 1) / 2) * TRACK

    position = {n: (x[n], y[depths[n]]) for n in depths}
    return Layout(
        {n: position[n] for n in spec.nodes},
        {e: [position[h] for h in hs] for e, hs in helpers.items()},
        {e: [track_y(depths[u], track_of.get((e, depths[u]), 0)) for u in chain[:-1]] for e, chain in chains.items()},
    )


def _tracks(chains, x, depths) -> tuple[dict, dict[int, int]]:
    """Give each horizontal edge segment a track in its gap between layers, so that different signals never share
    one (left-edge algorithm of channel routing).

    Segments of one signal share a track: the fan-out of a source, or else the edges merging into one target.
    Signals whose spans overlap get different tracks. Returns the track of each (edge, gap) and the number of
    tracks per gap.
    """
    segments = {}  # gap -> [(edge, x top, x bottom)]
    for edge, chain in chains.items():
        for u, v in zip(chain, chain[1:]):
            segments.setdefault(depths[u], []).append((edge, x[u], x[v]))

    track_of, counts = {}, {}
    for gap, segs in segments.items():
        fan_out = {}
        for (a, _), *_ in segs:
            fan_out[a] = fan_out.get(a, 0) + 1
        signal = {edge: ("from", edge[0]) if fan_out[edge[0]] > 1 else ("to", edge[1]) for edge, *_ in segs}

        span = {}
        for edge, top, bottom in segs:
            if abs(top - bottom) >= 1:  # Edges straight down need no track
                lo, hi = span.get(signal[edge], (top, top))
                span[signal[edge]] = min(lo, top, bottom), max(hi, top, bottom)

        track, current = {}, 0
        while len(track) < len(span):
            end = -math.inf
            for s in sorted((s for s in span if s not in track), key=lambda s: span[s]):
                if span[s][0] > end + 1:  # Signals touching at one point would look connected
                    track[s], end = current, span[s][1]
            current += 1
        counts[gap] = max(current, 1)
        track_of.update({(edge, gap): track.get(signal[edge], 0) for edge, *_ in segs})
    return track_of, counts


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
