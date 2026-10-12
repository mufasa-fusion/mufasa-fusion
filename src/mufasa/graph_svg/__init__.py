"""Render Fusion Graphs as interactive SVG, for ``Graph.plot_graph()`` and the docs' ``fusion-graph`` directive.

A graph is described as a :class:`GraphSpec` (``spec.py``), laid out (``layout.py``) and drawn (``draw.py``).
Port colors and icons come from the data type families (``families.py``); styles, hover script and icons are
plain files in this package.
"""

from mufasa.graph_svg.draw import FusionGraphSVG, asset, render, short_code
from mufasa.graph_svg.families import FAMILIES, UNKNOWN_FAMILY, Family, family_of, icon_of
from mufasa.graph_svg.layout import Layout, layout
from mufasa.graph_svg.spec import (
    FusionGraphCodeError,
    GraphSpec,
    NodeSpec,
    class_types,
    spec_from_code,
    spec_from_graph,
)
