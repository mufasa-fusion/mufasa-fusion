from mufasa.location import Location
from mufasa.io.outputs.base import OutputNode


class StreamingOutputNode(OutputNode):
    """Output node that delivers each result to a callable.

        out = StreamingOutputNode(my_callback)(prev_node)

    The callback receives one Location (or Observation) per alarm.
    ``on_output`` can also be reassigned at any time after construction.
    """

    _input_types = [Location]

    def __init__(self, on_output=None) -> None:
        super().__init__()
        self.on_output = on_output

    def process(self, item: Location) -> None:
        if self.on_output is not None:
            self.on_output(item)

    def get_config(self) -> dict:
        return {}
