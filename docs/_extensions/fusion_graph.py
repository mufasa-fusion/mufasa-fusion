"""Directive ``fusion-graph``: draws the Fusion Graph that a piece of example code builds.

The code is parsed, not executed (see :func:`mufasa.graph_svg.spec_from_code`), and drawn by
:mod:`mufasa.graph_svg`, the same code behind ``Graph.plot_graph()``. The docs build therefore needs MuFASA
installed. Options:

``:show-code:``
    Show the code next to the graph.
``:caption:``
    Caption of the code block (with ``:show-code:``).
``:class:``
    Extra CSS classes for the container.
"""

import hashlib
import re
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.application import Sphinx
from sphinx.directives.code import container_wrapper
from sphinx.environment import BuildEnvironment
from sphinx.util.docutils import SphinxDirective
from sphinx.util.typing import ExtensionMetadata

import mufasa
from mufasa import graph_svg

__version_info__ = 0, 1, 0
__version__ = ".".join(map(str, __version_info__))


class FusionGraphDirective(SphinxDirective):
    has_content = True
    option_spec = {
        "show-code": directives.flag,
        "caption": directives.unchanged,
        "class": directives.class_option,
    }

    def run(self) -> list[nodes.Node]:
        code = "\n".join(self.content)
        try:
            spec = graph_svg.spec_from_code(code)
        except graph_svg.FusionGraphCodeError as e:
            raise self.error(f"fusion-graph: {e}") from e

        # Ids inside the SVG must be unique on the page
        count = self.env.temp_data.get("fusion_graph_count", 0)
        self.env.temp_data["fusion_graph_count"] = count + 1
        prefix = f"fg-{re.sub(r'[^A-Za-z0-9]', '-', self.env.docname)}-{count}"
        _docs_with_graphs(self.env).add(self.env.docname)

        svg = graph_svg.render(spec, prefix=prefix, embed_assets=False)  # Styles and script are added per page
        graph = nodes.raw("", f'<figure class="mf-fusion-graph">{svg}</figure>', format="html")
        classes = self.options.get("class", [])
        if "show-code" not in self.options:
            return [nodes.container("", graph, classes=classes)] if classes else [graph]

        literal = nodes.literal_block(code, code, language="python")
        self.set_source_info(literal)
        if "caption" in self.options:
            literal = container_wrapper(self, literal, self.options["caption"])
        return [nodes.container("", literal, graph, classes=["mf-side-by-side", *classes])]


# --- Rebuild pages with graphs when the MuFASA code changes -------------------------------------------------
# Sphinx only re-reads pages whose source changed. Graphs also depend on the package (drawing code, node
# types), so pages with graphs are marked outdated whenever a source file of the package changes.

def _docs_with_graphs(env: BuildEnvironment) -> set[str]:
    if not hasattr(env, "fusion_graph_docs"):
        env.fusion_graph_docs = set()
    return env.fusion_graph_docs


def _package_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(mufasa.__file__).parent.rglob("*.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _outdated_graph_pages(app: Sphinx, env: BuildEnvironment, added, changed, removed) -> list[str]:
    current = _package_hash()
    if getattr(env, "fusion_graph_package_hash", None) == current:
        return []
    env.fusion_graph_package_hash = current
    return sorted(_docs_with_graphs(env) - set(removed))


def _purge_doc(app: Sphinx, env: BuildEnvironment, docname: str) -> None:
    _docs_with_graphs(env).discard(docname)


def _merge_info(app: Sphinx, env: BuildEnvironment, docnames, other: BuildEnvironment) -> None:
    _docs_with_graphs(env).update(_docs_with_graphs(other) & set(docnames))


# --- Styles and hover script, loaded once on each page with graphs ---------------------------------------------

ASSETS = ("graph.css", "graph.js")


def _add_assets_to_page(app: Sphinx, pagename: str, templatename, context, doctree) -> None:
    if pagename in _docs_with_graphs(app.env):
        app.add_css_file("fusion-graph/graph.css")
        app.add_js_file("fusion-graph/graph.js", defer="defer")


def _copy_assets(app: Sphinx, exception) -> None:
    if exception is None and app.builder.format == "html":
        target = Path(app.outdir, "_static", "fusion-graph")
        target.mkdir(parents=True, exist_ok=True)
        for name in ASSETS:
            target.joinpath(name).write_text(graph_svg.asset(name), encoding="utf-8")


def setup(app: Sphinx) -> ExtensionMetadata:
    app.add_directive("fusion-graph", FusionGraphDirective)
    app.connect("html-page-context", _add_assets_to_page)
    app.connect("build-finished", _copy_assets)
    app.connect("env-get-outdated", _outdated_graph_pages)
    app.connect("env-purge-doc", _purge_doc)
    app.connect("env-merge-info", _merge_info)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
