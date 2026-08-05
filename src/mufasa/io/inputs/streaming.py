import queue

from mufasa.location import Location, Observation
from mufasa.map import Map
from mufasa.io.inputs.base import InputNode
from mufasa.node import _NOT_SET

_STOP = object()


class StreamingInputNode(InputNode):
    """Base for push-based streaming inputs.

    External code (MQTT handler, socket listener, etc.) calls ingest() as
    items arrive. MuFASA is not responsible for connection lifecycle.
    Use LocationStreamingInput or MapStreamingInput directly.
    """

    _output_type = _NOT_SET

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.SimpleQueue = queue.SimpleQueue()

    def items(self):
        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            yield item

    def ingest(self, item) -> None:
        """Deliver one item into the pipeline."""
        self._queue.put(item)

    def stop(self) -> None:
        """Signal this input to stop yielding from items()."""
        self._queue.put(_STOP)

    def get_config(self) -> dict:
        return {}


class LocationStreamingInput(StreamingInputNode):
    """Streaming input for Location objects."""
    _output_type = Location
    
class ObservationStreamingInput(StreamingInputNode):
    """Streaming input for Location objects."""
    _output_type = Observation

class MapStreamingInput(StreamingInputNode):
    """Streaming input for Map objects."""
    _output_type = Map
