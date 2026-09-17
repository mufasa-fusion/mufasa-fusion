import os.path
from abc import ABCMeta, abstractmethod
from typing import Iterable

from autoapi._mapper import _link_objs
from docutils.nodes import Node
from docutils.statemachine import StringList
from jinja2 import Environment, FunctionLoader
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective, switch_source_input
from sphinx.util.parsing import nested_parse_to_nodes
from sphinx.util.typing import ExtensionMetadata

__version_info__ = 0, 1, 0
__version__ = ".".join(map(str, __version_info__))


class RstDirective(SphinxDirective, metaclass=ABCMeta):
    def run(self) -> list[Node]:
        source, lineno = self.state_machine.get_source_and_line(self.lineno)
        content = StringList()
        for line in self.run_rst():
            content.append(line, source, lineno)
        with switch_source_input(self.state, content):
            return nested_parse_to_nodes(self.state, content)

    @abstractmethod
    def run_rst(self) -> Iterable[str]:
        """Returns lines of rst to replace the directive with"""


class AutoApiJinjaDirective(RstDirective):
    """Render a selection of autoapi objects into a custom jinja2 template.

    The objects are specified in the directive's body, one fully qualified name per line.
    Separated by a blank line, the Jinja template's content follows. It must produce RST text.
    The list of objects is available as ``objs`` in the template.
    """

    has_content = True

    def run_rst(self) -> Iterable[str]:
        content = iter(self.content)
        # Collect objects from autoapi by name (one name on each line before the first blank one)
        all_objects = self.state.document.settings.env.autoapi_all_objects  # from autoapi
        objs = []
        for line in content:
            line = line.strip()
            if not line:
                break
            objs.append(all_objects[line])
        # Get the template from the remaining content and render it
        return JINJA_ENV.get_template(os.linesep.join(content)).render(objs=objs).split(os.linesep)


JINJA_ENV: Environment


def init_ext(app: Sphinx):
    global JINJA_ENV
    # Create a jinja env that behaves like autoapi's one (except it loads templates by treating their name as content)
    JINJA_ENV = Environment(loader=FunctionLoader(lambda src: src), lstrip_blocks=True, trim_blocks=True)
    JINJA_ENV.filters["prepare_docstring"] = lambda x: x
    JINJA_ENV.filters["link_objs"] = _link_objs
    prep_env = app.config.autoapi_prepare_jinja_env
    if prep_env is not None:
        prep_env(JINJA_ENV)


def setup(app: Sphinx) -> ExtensionMetadata:
    app.setup_extension("autoapi.extension")
    app.connect("builder-inited", init_ext, priority=400)  # Run before autoapi to access its settings unchanged
    app.add_directive("autoapi-template", AutoApiJinjaDirective)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
