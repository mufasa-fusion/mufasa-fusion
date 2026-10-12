"""Draws a graph description as SVG. Styles (graph.css), hover script (graph.js) and icons (icons/) are files
next to this module."""

import html
import itertools
import math
import re
from functools import cache
from importlib.resources import files

from mufasa.graph_svg.families import FAMILIES, TYPE_ICONS, UNKNOWN_FAMILY, Family, family_of, icon_of
from mufasa.graph_svg.layout import DY, Layout, layout
from mufasa.graph_svg.spec import GraphSpec

R = 34       # Node radius
PORT_R = 13  # Port radius

ASSETS = files("mufasa.graph_svg")
_ids = itertools.count()


def asset(name: str) -> str:
    return ASSETS.joinpath(name).read_text(encoding="utf-8")


@cache
def _icon_symbols() -> dict[str, tuple[str, str]]:
    """Icon name -> (viewBox, inner SVG content), read from icons/."""
    names = {f.icon for f in FAMILIES} | set(TYPE_ICONS.values()) | {UNKNOWN_FAMILY.icon}
    symbols = {}
    for name in names:
        svg = asset(f"icons/{name}.svg")
        view_box = re.search(r'viewBox="([^"]+)"', svg).group(1)
        symbols[name] = view_box, re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    return symbols


def short_code(name: str) -> str:
    """A 2-3 letter code for a class name: ``BayesianFusion`` -> ``BF``, ``POM`` -> ``POM``, ``Threshold`` -> ``TH``."""
    words = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", name) or [name]
    if len(words) > 1:
        return "".join(w[0] for w in words)[:3].upper()
    return words[0] if words[0].isupper() and len(words[0]) <= 4 else words[0][:2].upper()


def render(spec: GraphSpec, prefix: str | None = None, embed_assets: bool = True) -> str:
    """Draw a graph description as an SVG string.

    ``prefix`` makes ids unique when several graphs share a page. With ``embed_assets`` the SVG carries its own
    styles and hover script (e.g. for notebooks); without, the page must load graph.css and graph.js.
    """
    prefix = prefix or f"mfg{next(_ids)}"
    lay = layout(spec)
    in_ports, out_ports = {}, {}
    for n, node in spec.nodes.items():
        in_ports[n] = _ports(*lay.nodes[n], node.input_types, top=True)
        out_ports[n] = _ports(*lay.nodes[n], [node.output_type] if node.output_type else [], top=False)

    edges = [_edge(a, b, spec, lay, out_ports, in_ports) for a, b in spec.edges if out_ports[a] and in_ports[b]]
    nodes = [_node(n, node, lay.nodes[n], in_ports[n] | out_ports[n], prefix) for n, node in spec.nodes.items()]

    # Room on the right for the names that slide out on hover
    label_room = min(max(len(node.cls.__name__) for node in spec.nodes.values()) * 9 + 20, 190)
    left, right, pad_y = R + PORT_R, R + label_room, R + PORT_R + 6
    points = [*lay.nodes.values(), *(point for bends in lay.bends.values() for point in bends)]
    width = max(x for x, _ in points) + left + right
    height = max(y for _, y in points) + 2 * pad_y

    symbols = "".join(f'<symbol id="{prefix}-{name}" viewBox="{view_box}">{content}</symbol>'
                      for name, (view_box, content) in _icon_symbols().items())
    assets = f"<style>{asset('graph.css')}</style><script>{asset('graph.js')}</script>" if embed_assets else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="mf-fg" viewBox="{-left} {-pad_y} {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" style="max-width: 100%; height: auto" role="img" aria-label="Fusion Graph">'
            f'<defs>{symbols}</defs>{"".join(edges)}{"".join(nodes)}{assets}</svg>')


def _ports(x: float, y: float, types: list[type], top: bool) -> dict[tuple[Family, bool], tuple[float, float, type]]:
    """One port per family on the top (inputs) or bottom (output) rim, spread out if there are several."""
    by_family = {}
    for t in types:
        by_family.setdefault(family_of(t), t)
    ports = {}
    for i, (family, t) in enumerate(by_family.items()):
        dx = (i - (len(by_family) - 1) / 2) * (2 * PORT_R + 4)
        dy = math.sqrt(max(R * R - dx * dx, 0))
        ports[family, top] = (x + dx, y - dy if top else y + dy, t)
    return ports


def _edge(a: str, b: str, spec: GraphSpec, lay: Layout, out_ports, in_ports) -> str:
    """Right-angle route from an output port down to the matching input port, through the bends of skipped layers.

    Between two layers the edge runs vertically, crosses over halfway between them, and continues vertically.
    """
    family = family_of(spec.nodes[a].output_type)
    x1, y1, _ = out_ports[a].get((family, False), next(iter(out_ports[a].values())))
    x2, y2, _ = in_ports[b].get((family, True), next(iter(in_ports[b].values())))
    y1, y2 = y1 + PORT_R, y2 - PORT_R

    corners, x = [(x1, y1)], x1
    for next_x, layer_y in [*lay.bends.get((a, b), []), (x2, lay.nodes[b][1])]:
        if abs(next_x - x) >= 1:
            corners += [(x, layer_y - DY / 2), (next_x, layer_y - DY / 2)]
            x = next_x
    corners.append((x2, y2))

    return (f'<g class="mf-edge" style="--mf-fam:{family.color}" data-from="{html.escape(a)}" data-to="{html.escape(b)}">'
            f'<path d="{_rounded_path(corners)}"/><circle cx="{x1:.1f}" cy="{y1:.1f}" r="3.5"/>'
            f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="3.5"/></g>')


def _rounded_path(points: list[tuple[float, float]], radius: float = 10) -> str:
    """A path through ``points`` with rounded corners."""
    def toward(p, q, distance):
        t = distance / math.dist(p, q)
        return f"{p[0] + (q[0] - p[0]) * t:.1f} {p[1] + (q[1] - p[1]) * t:.1f}"

    path = f"M{points[0][0]:.1f} {points[0][1]:.1f}"
    for prev, corner, nxt in zip(points, points[1:], points[2:]):
        r = min(radius, math.dist(prev, corner) / 2, math.dist(corner, nxt) / 2)
        path += f" L{toward(corner, prev, r)} Q{corner[0]:.1f} {corner[1]:.1f} {toward(corner, nxt, r)}"
    return path + f" L{points[-1][0]:.1f} {points[-1][1]:.1f}"


def _node(n: str, node, position: tuple[float, float], ports: dict, prefix: str) -> str:
    x, y = position
    name = html.escape(node.cls.__name__)
    if node.is_input != node.is_output:  # Input or Output node: flat on the boundary side
        body, role = f'<path d="{_boundary_path(x, y, flat_top=node.is_input)}" class="mf-body"/>', "mf-io"
    else:
        body, role = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{R}" class="mf-body"/>', "mf-proc"
    badges = "".join(_port(prefix, px, py, t, family) for (family, _), (px, py, t) in ports.items())
    return (f'<g class="mf-node {role}" data-id="{html.escape(n)}" tabindex="0" aria-label="{name}">{body}'
            f'<text x="{x:.1f}" y="{y + 5.5:.1f}" text-anchor="middle" class="mf-code">{short_code(node.cls.__name__)}</text>'
            f'<text x="{x + R + 12:.1f}" y="{y + 5:.1f}" class="mf-name">{name}</text>{badges}</g>')


def _boundary_path(x: float, y: float, flat_top: bool) -> str:
    """Flat edge with rounded corners on the boundary side, half circle towards the rest of the graph."""
    s = -1 if flat_top else 1  # Direction of the flat side
    h, c = R * 0.9, 7          # Distance of the flat side from the center, corner radius
    return (f"M{x + s * R:.1f} {y:.1f} V{y + s * (h - c):.1f} Q{x + s * R:.1f} {y + s * h:.1f} {x + s * (R - c):.1f} "
            f"{y + s * h:.1f} H{x - s * (R - c):.1f} Q{x - s * R:.1f} {y + s * h:.1f} {x - s * R:.1f} "
            f"{y + s * (h - c):.1f} V{y:.1f} A{R} {R} 0 0 1 {x + s * R:.1f} {y:.1f} Z")


def _port(prefix: str, cx: float, cy: float, data_type: type, family: Family) -> str:
    """A badge with the family icon; hovering it slides out a second badge with the concrete type."""
    def badge(icon: str) -> str:
        size = PORT_R * 1.15
        return (f'<circle r="{PORT_R}" class="mf-port-bg"/><use href="#{prefix}-{icon}" x="{-size / 2:.1f}" '
                f'y="{-size / 2:.1f}" width="{size:.1f}" height="{size:.1f}"/>')

    type_name = html.escape(data_type.__name__)
    family_name = "Unknown" if family is UNKNOWN_FAMILY else family.root.__name__
    return (f'<g class="mf-port" style="--mf-fam:{family.color}" transform="translate({cx:.1f} {cy:.1f})">'
            f'<title>{family_name} family: {type_name}</title><g class="mf-sub">{badge(icon_of(data_type))}'
            f'<text x="{PORT_R + 5}" y="4" class="mf-sub-label">{type_name}</text></g>{badge(family.icon)}</g>')


class FusionGraphSVG:
    """A rendered Fusion Graph. Displays itself in Jupyter notebooks; ``save()`` writes an .svg file."""

    def __init__(self, svg: str):
        self.svg = svg

    def _repr_html_(self) -> str:
        return self.svg

    def __str__(self) -> str:
        return self.svg

    def save(self, path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.svg)
