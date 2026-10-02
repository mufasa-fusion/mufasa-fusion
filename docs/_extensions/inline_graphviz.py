"""Tweaks graphviz rendering so that SVG output is inlined in HTML (instead of using <object>)"""

from typing import Any

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.ext.graphviz import graphviz, render_dot_html, \
    latex_visit_graphviz, texinfo_visit_graphviz, text_visit_graphviz, man_visit_graphviz
from sphinx.util import logging
from sphinx.writers.html5 import HTML5Translator

__version_info__ = 0, 1, 0
__version__ = ".".join(map(str, __version_info__))

logger = logging.getLogger(__name__)


def render_dot_html_inline_svg(
    self: HTML5Translator,
    node: graphviz,
    code: str,
    options: dict[str, Any],
    prefix: str = 'graphviz',
    imgcls: str | None = None,
    alt: str | None = None,
    filename: str | None = None,
) -> tuple[str, str]:
    output_format = self.builder.config.graphviz_output_format
    try:
        return render_dot_html(self, node, code, options, prefix, imgcls, alt, filename)
    except nodes.SkipNode as skip:
        if skip.__cause__ is None and output_format == "svg":
            # Modify the body to contain the SVG content rather than an <object> referencing the SVG
            has_align_div = "align" in node
            svg_body_index = -3 - has_align_div  # Index from body end at which the added content starts
            svg_path = self.builder.outdir / self.body[svg_body_index].split("\"")[1]

            del self.body[svg_body_index:]

            with open(svg_path) as svg_file:
                # Skip header of standalone document (TODO render dot with -Tsvg_inline instead of -T{format})
                for line in svg_file:
                    if line.startswith("<svg"):
                        self.body.append(line)
                        break
                self.body.extend(svg_file)

            if has_align_div:
                self.body.append("</div>\n")
        raise


def html_visit_graphviz(self: HTML5Translator, node: graphviz) -> None:
    render_dot_html_inline_svg(self, node, node["code"], node["options"], filename=node.get("filename"))


def setup(app: Sphinx):
    app.setup_extension("sphinx.ext.graphviz")
    app.add_node(
        graphviz,
        override=True,
        html=(html_visit_graphviz, None),
        latex=(latex_visit_graphviz, None),
        texinfo=(texinfo_visit_graphviz, None),
        text=(text_visit_graphviz, None),
        man=(man_visit_graphviz, None),
    )

    return {
        "version": __version__,
        "parallel_read_safe": True,
    }
