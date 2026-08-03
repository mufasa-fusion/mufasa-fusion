from mufasa.location import Observation, Location
from mufasa.map import Map
from mufasa.io.inputs.base import InputNode


class LocationInput(InputNode):

    _input_types = []
    """Wraps an in-memory collection of Location or Observation objects.

    Accepts any iterable (list, generator, tuple). If the collection
    contains Observations or Locations, they are returned sorted by timestamp.
    """

    def __init__(self, data) -> None:
        self._data: list[Location] = list(data)
        if not self._data:
            raise ValueError("LocationInput requires a non-empty collection")
        self._output_type: type = (
            Observation if all(isinstance(item, Observation) for item in self._data) else Location
        )
        super().__init__()

    @property
    def output_type(self) -> type:
        return self._output_type

    def items(self) -> list[Location]:
        return sorted(self._data, key=lambda e: e.timestamp)

    def get_config(self) -> dict:
        raise TypeError(
            "LocationInput holds in-memory data and cannot be serialized to a config file. "
            "Use GeoJsonInput for serializable file-based input."
        )


class MapInput(InputNode):

    _input_types = []
    _output_type = Map
    """Wraps an in-memory collection of Map objects.

    Accepts any iterable (list, generator, tuple). Maps that carry a
    timestamp are dispatched in timestamp order; maps without a timestamp
    are dispatched in the order they were given.
    """

    def __init__(self, data) -> None:
        super().__init__()
        self._data: list[Map] = list(data)
        if not self._data:
            raise ValueError("MapInput requires a non-empty collection")
        if not all(isinstance(item, Map) for item in self._data):
            raise TypeError("MapInput only accepts Map objects")

    def items(self) -> list[Map]:
        return sorted(self._data, key=lambda m: m.timestamp)

    def get_config(self) -> dict:
        raise TypeError(
            "MapInput holds in-memory data and cannot be serialized to a config file. "
            "Use GeoTiffInput for serializable file-based input."
        )
