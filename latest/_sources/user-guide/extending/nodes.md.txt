---
file_format: mystnb
---

```{code-cell}
:tags: [remove-cell]
import os.path
os.chdir(os.path.join("..", "..", "_data"))
```

# Writing a Node

Every step in a Fusion Graph is a {class}`~mufasa.node.Node`.
To add your own processing, data source or result sink, you subclass it and declare four things:

| | |
|---|---|
| {attr}`~mufasa.node.Node._input_types` | The data types the node accepts. `[]` for input nodes. |
| {attr}`~mufasa.node.Node._output_type` | The data type the node produces. `None` for output nodes. |
| {func}`~mufasa.node.Node.process` | What the node does with each piece of data it receives. |
| {func}`~mufasa.node.Node.get_config` | The constructor arguments, so a graph using the node can be saved and loaded. |

The examples on this page are small on purpose. Each one shows a different kind of node,
and each one runs in a Fusion Graph with the sample data from the {doc}`../tips-and-tricks`.
They all share the same spatial setup:

```{code-cell}
from mufasa import Graph, BoundingBox

BBOX = BoundingBox(16.4255, 48.2675, 16.4295, 48.2710)  # WGS84: lon/lat
CRS = "EPSG:32633"  # UTM zone 33N, so the graph computes in metres
RESOLUTION = (5, 5)  # map cell size in metres
```

## Processing Nodes

Processing nodes hold the fusion logic. They have both input and output types,
and sit between the input and output nodes of a Fusion Graph.

### ConfidenceBoost

The simplest kind of node receives one {class}`~mufasa.location.Observation` at a time
and passes one (or more) on to its successors.
This one raises the confidence of every observation by a fixed factor:

```{code-cell}
from mufasa.node import Node
from mufasa.location import Observation


class ConfidenceBoost(Node):
    """Multiplies every observation's confidence by a fixed factor."""

    _input_types = [Observation]  # accepts Observation (and any subclass)
    _output_type = Observation  # emits Observation

    def __init__(self, factor: float = 1.2) -> None:
        super().__init__()
        self.factor = factor

    def process(self, obs: Observation) -> None:
        boosted = Observation(
            geometry=obs.geometry,
            timestamp=obs.timestamp,
            properties=obs.properties,
            confidence=min(obs.confidence * self.factor, 1.0),
        )
        for successor in self._successors:
            successor.process(boosted)

    def get_config(self) -> dict:
        return {"factor": self.factor}
```

Wire it between an input and an output node like any built-in node:

```{code-cell}
from mufasa.io.inputs import GeoJsonInput
from mufasa.io.outputs import LocationOutput

src = GeoJsonInput("sensor_b.geojson")
boost = ConfidenceBoost(factor=1.5)(src)
out = LocationOutput()(boost)

graph = Graph([src], [out], crs=CRS, bbox=BBOX, resolution=RESOLUTION)
graph.plot_graph()
```

```{code-cell}
graph.run()

[(round(before.confidence, 2), round(after.confidence, 2)) for before, after in zip(src.items(), out.result)]
```

Each pair shows an observation's confidence before and after the boost, capped at 1.0.

### ComfortZone

Nodes that process maps work differently. They aren't handed the data. Instead, they are told that their predecessor has a new map,
read it from `self._predecessors[n].map`, and call `self._trigger_successors()` once their own map is ready.
They also create their map once, in {func}`~mufasa.node.Node.configure`, when the graph tells every node its spatial setup.

This node ignores detections inside a zone you know is safe, for example where your own patrol vehicle is parked,
so they don't raise alarms. It takes the {class}`~mufasa.map.BayesianMap` of a {class}`~mufasa.nodes.mapping.POM`,
converts it to a plain probability {class}`~mufasa.map.Map`, and sets the probability inside the zone to zero.
Which map cells the zone covers only depends on the spatial setup, so the node works that out once, in `configure()`:

```{code-cell}
import numpy as np
import shapely
from pyproj import Transformer
from rasterio.features import geometry_mask

from mufasa.map import BayesianMap, Map


class ComfortZone(Node):
    """Ignores detections inside a zone you know is safe, such as your own base."""

    _input_types = [BayesianMap]
    _output_type = Map

    def __init__(self, zone_wkt: str) -> None:
        super().__init__()
        self.zone_wkt = zone_wkt  # polygon in WGS84 (lon/lat), as WKT so it can be saved and loaded
        self._map: Map | None = None
        self._inside: np.ndarray | None = None

    def configure(self, crs, bbox, resolution) -> None:
        self._map = Map.from_bounds(bbox, resolution, crs)
        # Project the zone into the graph's CRS and mark the map cells it covers, once
        to_crs = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
        zone = shapely.transform(shapely.from_wkt(self.zone_wkt), to_crs, interleaved=False)
        self._inside = geometry_mask(
            [zone], out_shape=self._map.data.shape, transform=self._map.transform, invert=True,
        )

    def process(self) -> None:
        src = self._predecessors[0].map
        self._map.data[:] = src.probabilities
        self._map.data[self._inside] = 0.0  # nothing to worry about in here
        self._map.timestamp = src.timestamp
        self._trigger_successors()

    @property
    def map(self) -> Map:
        return self._map

    def get_config(self) -> dict:
        return {"zone_wkt": self.zone_wkt}
```

To make the detections visible on the map, we give them a spatial extent with the `radius` property (in metres):
the first one, a large event right where our own patrol vehicle is parked, gets 30 m, the others 15 m.

```{code-cell}
import dataclasses

from mufasa.io.inputs import LocationInput
from mufasa.io.outputs import MapOutput
from mufasa.nodes.mapping import POM

zone = shapely.box(16.4260, 48.2680, 16.4273, 48.2689)  # where our own patrol vehicle is parked

detections = [
    dataclasses.replace(obs, properties={**obs.properties, "radius": 30 if i == 0 else 15})
    for i, obs in enumerate(GeoJsonInput("sensor_b.geojson").items())
]

src = LocationInput(detections)
pom = POM(decay_s=60)(src)
comfort = ComfortZone(zone.wkt)(pom)
out = MapOutput()(comfort)

graph = Graph([src], [out], crs=CRS, bbox=BBOX, resolution=RESOLUTION)
graph.plot_graph()
```

```{code-cell}
graph.run()
```

The detection inside the zone (dashed) disappears, all others stay:

```{code-cell}
:tags: [hide-input]
import contextily as cx
import matplotlib.pyplot as plt

zone_xy = shapely.transform(zone, Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform, interleaved=False)
b = comfort.map.bbox
extent = (b.min_x, b.max_x, b.min_y, b.max_y)

fig, axes = plt.subplots(1, 2, figsize=(9, 4.5), sharey=True)
for ax, data, title in [
    (axes[0], pom.map.probabilities, "POM probabilities"),
    (axes[1], comfort.map.data, "ComfortZone"),
]:
    # Only show cells that carry information: not the prior (0.5), not the zeroed zone
    shown = np.ma.masked_where(np.isclose(data, 0.5) | (data == 0), data)
    image = ax.imshow(shown, extent=extent, vmin=0, vmax=1, cmap="viridis", zorder=2)
    ax.plot(*zone_xy.exterior.xy, color="black", linewidth=1, linestyle="--", zorder=3)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    cx.add_basemap(ax, crs=CRS, source=cx.providers.Esri.WorldStreetMap, attribution_size=6)
    ax.set_title(title)
    ax.set_axis_off()
fig.colorbar(image, ax=axes, shrink=0.8, label="probability");
```

## IO Nodes

Input and output nodes form the boundary of a Fusion Graph. They connect it to files and external systems,
and convert between their formats and MuFASA's data models.

(writing-input-nodes)=
### CsvInput

Input nodes bring data into a Fusion Graph.
They have no input types, and instead of `process()` they implement
{func}`~mufasa.io.inputs.base.InputNode.items`, which returns the data in temporal order.
Coordinates are expected in WGS84; the graph projects them into its CRS for you.

This one reads detections from a CSV file like this:

```text
timestamp,lon,lat,confidence
0,16.42664,48.26841,0.94
2,16.42684,48.26916,0.55
4,16.42712,48.26962,0.79
```

```{code-cell}
:tags: [remove-cell]
import tempfile

csv_path = os.path.join(tempfile.mkdtemp(), "detections.csv")
with open(csv_path, "w") as f:
    f.write(
        "timestamp,lon,lat,confidence\n"
        "0,16.42664,48.26841,0.94\n"
        "2,16.42684,48.26916,0.55\n"
        "4,16.42712,48.26962,0.79\n"
    )
```

```{code-cell}
import csv

from shapely.geometry import Point

from mufasa.io.inputs import InputNode


class CsvInput(InputNode):
    """Reads detections from a CSV file with timestamp, lon, lat and confidence columns."""

    _output_type = Observation

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    def items(self) -> list[Observation]:
        with open(self.path, newline="") as f:
            rows = list(csv.DictReader(f))
        return [
            Observation(
                geometry=Point(float(row["lon"]), float(row["lat"])),
                timestamp=float(row["timestamp"]),
                confidence=float(row["confidence"]),
            )
            for row in rows
        ]

    def get_config(self) -> dict:
        return {"path": self.path}
```

```{code-cell}
src = CsvInput(csv_path)
src.items()
```

:::{seealso}
{doc}`sources` shows how to write input nodes for live data, from sensors and messaging systems.
:::

### AlarmPrinter

Output nodes take the results of a Fusion Graph to the outside world: files, dashboards, alarm systems.
They have no output type. Locations arrive in the graph's CRS, so
`self._to_wgs84()` converts them back to longitude and latitude.

This one raises an alarm for every observation above a confidence threshold:

```{code-cell}
from mufasa.io.outputs import OutputNode


class AlarmPrinter(OutputNode):
    """Prints an alarm for every observation above a confidence threshold."""

    _input_types = [Observation]

    def __init__(self, threshold: float = 0.8) -> None:
        super().__init__()
        self.threshold = threshold

    def process(self, obs: Observation) -> None:
        if obs.confidence >= self.threshold:
            obs = self._to_wgs84(obs)
            print(
                f"ALARM t={obs.timestamp:g}s at ({obs.geometry.x:.5f}, {obs.geometry.y:.5f}),"
                f" confidence {obs.confidence:.2f}"
            )

    def get_config(self) -> dict:
        return {"threshold": self.threshold}
```

Combined with the input node from above:

```{code-cell}
src = CsvInput(csv_path)
alarm = AlarmPrinter(threshold=0.75)(src)

graph = Graph([src], [alarm], crs=CRS, bbox=BBOX, resolution=RESOLUTION)
graph.plot_graph()
```

```{code-cell}
graph.run()
```

If an output node collects results and writes them at the end, for example to a file,
override {func}`~mufasa.io.outputs.base.OutputNode.save`. The graph calls it once all inputs have been processed.

:::{admonition} Coming Soon
:class: admonition-todo
Input and output nodes for (Geo)Pandas DataFrames, so you can feed a `GeoDataFrame` straight into a Fusion Graph
and collect its results as one. Until then, see {ref}`geopandas-integration` in the {doc}`../tips-and-tricks`.
:::

## Saving and Loading

{func}`Graph.to_config() <mufasa.graph.Graph.to_config>` stores a Fusion Graph as a JSON-serializable dict,
using each node's `get_config()`. To load it again with {func}`Graph.from_config() <mufasa.graph.Graph.from_config>`,
register your node in the {attr}`~mufasa.registry.NODE_REGISTRY`. The key must match the class name exactly:

```{code-cell}
from mufasa.registry import NODE_REGISTRY

NODE_REGISTRY["ConfidenceBoost"] = ConfidenceBoost

src = GeoJsonInput("sensor_b.geojson")
out = LocationOutput()(ConfidenceBoost(factor=1.5)(src))
config = Graph([src], [out], crs=CRS, bbox=BBOX, resolution=RESOLUTION).to_config()

restored = Graph.from_config(config)
restored.plot_graph()
```

See {ref}`dict-config` for more on saving and loading Fusion Graphs.

## Checklist

| | Requirement |
|---|---|
| &#9744; | `_input_types` declared (`[]` for input nodes) |
| &#9744; | `_output_type` declared (`None` for output nodes) |
| &#9744; | `process()` implemented (`items()` for input nodes) |
| &#9744; | `get_config()` returns all constructor arguments as a JSON-serializable dict |
| &#9744; | Registered in the `NODE_REGISTRY`, so graphs using the node can be saved and loaded |
| &#9744; | `configure()` overridden if the node needs the spatial setup, for example to create a map |
| &#9744; | `reset()` overridden if the node holds state that must be cleared between runs (see {func}`Graph.reset() <mufasa.graph.Graph.reset>`) |

:::{tip}
Want to contribute your node to MuFASA? Propose it with the *New node* issue template first.
Its definition of done extends this checklist with tests and documentation.
:::
