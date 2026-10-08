"""Graph descriptions: nodes with their data types, and edges. Built from a Graph or from example code."""

import ast
import builtins
import importlib
from dataclasses import dataclass, field

from mufasa.node import Node, _NOT_SET


@dataclass
class NodeSpec:
    id: str
    cls: type
    input_types: list[type]
    output_type: type | None

    @property
    def is_input(self) -> bool:
        return not self.input_types

    @property
    def is_output(self) -> bool:
        return self.output_type is None


@dataclass
class GraphSpec:
    nodes: dict[str, NodeSpec] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)


class FusionGraphCodeError(ValueError):
    def __init__(self, message: str, lineno: int | None = None):
        super().__init__(f"line {lineno}: {message}" if lineno else message)


def _sorted_types(types) -> list[type]:
    return sorted(types, key=lambda t: t.__name__)


def spec_from_graph(graph) -> GraphSpec:
    """Describe a built Graph, with the data types its nodes resolved at construction and wiring."""
    from mufasa.graph import _real_successors

    spec = GraphSpec()
    ids = {}
    for node in graph.nodes:
        ids[id(node)] = node.name
        spec.nodes[node.name] = NodeSpec(node.name, type(node), _sorted_types(node.input_types), node.output_type)
    for node in graph.nodes:
        spec.edges += [(node.name, ids[id(succ)]) for succ in _real_successors(node) if id(succ) in ids]
    return spec


def class_types(cls: type) -> tuple[list[type], type | None]:
    """Data types declared by a node class.

    Nodes that resolve their types later (at construction or wiring) declare their broadest valid types on the
    class, so a graph drawn from code shows what a class accepts and produces in general.
    """
    input_types = [] if cls._input_types is _NOT_SET else _sorted_types(cls._input_types)
    output_type = None if cls._output_type is _NOT_SET else cls._output_type
    return input_types, output_type


def spec_from_code(source: str) -> GraphSpec:
    """Describe the graph that example code builds, without running it.

    Understands ``from module import NodeClass`` and assignments ``name = NodeClass(...)`` (a source) or
    ``name = NodeClass(...)(input, ...)``. Everything else, such as ``Graph(...)`` or ``graph.run()``, is ignored.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise FusionGraphCodeError(f"invalid Python: {e.msg}", e.lineno) from e

    imported = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module:
            module = importlib.import_module(stmt.module)
            imported.update({alias.asname or alias.name: getattr(module, alias.name) for alias in stmt.names})

    spec = GraphSpec()
    for stmt in tree.body:
        match stmt:
            case ast.Assign(targets=[ast.Name(id=name)], value=ast.Call(func=ast.Call(func=ast.Name(id=class_name)), args=args)):
                inputs = args
            case ast.Assign(targets=[ast.Name(id=name)], value=ast.Call(func=ast.Name(id=class_name))):
                inputs = []
            case _:
                continue

        cls = imported.get(class_name, getattr(builtins, class_name, None))
        if cls is None:
            raise FusionGraphCodeError(f"unknown name '{class_name}'", stmt.lineno)
        if not (isinstance(cls, type) and issubclass(cls, Node)):
            continue  # E.g. graph = Graph(...)

        spec.nodes[name] = NodeSpec(name, cls, *class_types(cls))
        for arg in inputs:
            if not (isinstance(arg, ast.Name) and arg.id in spec.nodes):
                raise FusionGraphCodeError("node inputs must be names of previously defined nodes", stmt.lineno)
            spec.edges.append((arg.id, name))

    if not spec.nodes:
        raise FusionGraphCodeError("no nodes found; expected assignments like 'pom = POM(decay_s=5)(track)'")
    return spec
