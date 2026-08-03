from abc import ABC, abstractmethod


class _NotSet:
    """Sentinel for class attributes that must be defined by subclasses."""
    def __repr__(self) -> str:
        return "_NOT_SET"


_NOT_SET = _NotSet()


class Node(ABC):
    """Base class for all pipeline nodes.

    Every concrete subclass must declare two class attributes::

        class MyNode(Node):
            _input_types = [Location]       # types this node accepts; [] for source nodes
            _output_type = Observation      # type this node emits; None for sink nodes

    Listing a parent type (e.g. ``Location``) automatically covers all
    subclasses (e.g. ``Observation``) because wiring uses ``issubclass``.

    Two methods must be implemented by every concrete subclass:

    ``process(*args, **kwargs)``
        Called by the framework to push data through the node. Use the
        signature appropriate for this node's role — see the docstring on
        :meth:`process` for the standard patterns.

    ``get_config() -> dict``
        Return all constructor arguments as a plain JSON-serializable dict
        so the pipeline can be saved and reconstructed.

    Two further methods have no-op defaults and should be overridden by nodes
    that accumulate internal state across ``process()`` calls:

    ``flush() -> None``
        Called by the framework after all inputs are exhausted (end of
        stream). Emit any observations or map snapshots remaining in an
        internal buffer. Stateless nodes can leave this as the no-op default.

    ``reset() -> None``
        Called by the framework between pipeline runs. Clear all runtime
        state so the pipeline can be re-run cleanly without constructing a
        new instance. Stateless nodes can leave this as the no-op default.
    """

    _input_types: list = _NOT_SET
    _output_type: "type | None" = _NOT_SET

    def __init__(self) -> None:
        cls = type(self)

        if cls._input_types is _NOT_SET:
            raise TypeError(
                f"{cls.__name__} must define _input_types as a class attribute.\n"
                "  _input_types = []         # source node — accepts no input\n"
                "  _input_types = [Location] # accepts Location and all subclasses\n"
                "  _input_types = [Map]      # accepts Map and all subclasses"
            )

        # Allow subclasses that override the output_type property directly
        # (e.g. nodes whose output type is determined at construction time).
        output_type_is_overridden = cls.output_type is not Node.output_type
        if cls._output_type is _NOT_SET and not output_type_is_overridden:
            raise TypeError(
                f"{cls.__name__} must define _output_type as a class attribute.\n"
                "  _output_type = None        # sink node — produces no output\n"
                "  _output_type = Observation # produces Observation objects\n"
                "  _output_type = Map         # produces Map objects"
            )

        self._predecessors: list["Node"] = []
        self._successors:   list["Node"] = []
        self.name: str | None = None

    def __call__(self, *inputs: "Node") -> "Node":
        for inp in inputs:
            if inp.output_type is None:
                raise TypeError(
                    f"{type(inp).__name__} has no output type and cannot be used as input"
                )
            if not any(
                issubclass(inp.output_type, t) for t in self.input_types
            ):
                raise TypeError(
                    f"{type(inp).__name__} outputs {inp.output_type.__name__} "
                    f"but {type(self).__name__} accepts "
                    f"{[t.__name__ for t in self.input_types]}"
                )
            self._predecessors.append(inp)
            inp._successors.append(self)
        return self

    def configure(self, crs: str, bbox, resolution: tuple) -> None:
        """Receive spatial configuration from the Graph at construction time.

        Override in nodes that need crs/bbox/resolution to initialise
        internal state (e.g. POM creates its map here). Default is a no-op.
        """

    def _trigger_successors(self) -> None:
        for successor in self._successors:
            successor.process()

    @property
    def input_types(self) -> frozenset:
        """Types this node accepts as input. Derived from ``_input_types``."""
        return frozenset(type(self)._input_types)

    @property
    def output_type(self) -> "type | None":
        """Type this node emits. Derived from ``_output_type``."""
        return type(self)._output_type

    @abstractmethod
    def process(self, *args, **kwargs) -> None:
        """Process incoming data and forward results to successors.

        Override with the signature appropriate for this node's role:

        **Observation-consuming nodes** receive one observation per call::

            def process(self, obs: Observation) -> None:
                result = ...                    # compute result
                for succ in self._successors:
                    succ.process(result)        # push to downstream nodes

        **Map-consuming nodes** are called with no arguments and read
        their input from the predecessor via its ``.map`` attribute::

            def process(self) -> None:
                m = self._predecessors[0].map   # read upstream map
                ...                             # update self.map in place
                self._trigger_successors()      # notify downstream nodes

        **Sink nodes** collect data without emitting anything further::

            def process(self, obs: Observation) -> None:
                self._collected.append(obs)
        """

    def flush(self) -> None:
        """Emit any buffered output remaining at end of stream.

        Called by the framework after all inputs are exhausted. Override in
        nodes that accumulate observations or map data across multiple
        ``process()`` calls before emitting (e.g. scan-window trackers,
        batch clusterers). The default is a no-op — stateless nodes need not
        override this.
        """

    def reset(self) -> None:
        """Clear all runtime state, returning the node to its post-init condition.

        Called by the framework between pipeline runs so the same node
        instance can process a fresh dataset without being reconstructed.
        Override in nodes that hold mutable state (buffers, accumulators,
        fitted models). The default is a no-op — stateless nodes need not
        override this.
        """

    @abstractmethod
    def get_config(self) -> dict:
        """Return all constructor arguments as a plain JSON-serializable dict.

        Used by ``Graph.to_config()`` to serialise the pipeline. Every key
        must be a string; every value must be JSON-serializable.
        """
