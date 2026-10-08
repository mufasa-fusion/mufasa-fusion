---
file_format: mystnb
---

```{code-cell}
:tags: [remove-cell]
import os.path
os.chdir(os.path.join("..", "_data"))
```

# Design principles

MuFASA is built on three principles. The colors on this page mark where each one shows up,
in the architecture and in a complete example.

::::{container} mf-principles-legend

:::{container} mf-legend-io
**Detection level**

MuFASA works on detections, not raw signals. Only the Input and Output nodes deal with files
and formats. Everything in between works on Locations and Maps.
:::

:::{container} mf-legend-proc
**Explicit architecture**

A fusion system is a graph of nodes that connect wherever their data types match.
The wiring is the code, and every stage stays inspectable.
:::

:::{container} mf-legend-graph
**Rapid prototyping**

A complete graph takes about ten lines of Python, with every parameter in plain sight.
The same graph runs on recorded data and, with streaming inputs, on live data.
:::

::::

## Where MuFASA sits

A Fusion Graph sits between your perception and your decision support. Its Input and Output nodes
form the boundary to the outside world, and its Processing nodes hold the fusion logic.

:::::{container} mf-stack

::::{container} mf-stack-outer
**Sensors & perception**

Cameras, radar, …
::::

::::{container} mf-stack-graph

:::{container} mf-stack-io
**Input nodes**

Translate detections
:::

:::{container} mf-stack-proc
**Processing nodes**

Fuse and detect
:::

:::{container} mf-stack-io
**Output nodes**

Translate results
:::

::::

::::{container} mf-stack-outer
**Decision support**

Alarms, operators
::::

:::::

## The principles in an example

This graph fuses two sensors with a static prior and turns the result into alarms.

```{code-cell}
:class: mf-annotated

from mufasa import Graph, BoundingBox
from mufasa.io.inputs import GeoJsonInput
from mufasa.io.outputs import GeoJsonOutput
from mufasa.nodes import StaticMap, POM, BayesianFusion, Threshold

# Input nodes
track_a = GeoJsonInput("sensor_a.geojson")
track_b = GeoJsonInput("sensor_b.geojson")
static = StaticMap("priors.geojson")

# Processing nodes
pom_a = POM(decay_s=5)(track_a)
pom_b = POM(decay_s=1)(track_b)
fused = BayesianFusion()(pom_a, pom_b, static)
alarms = Threshold(threshold=0.7)(fused)

# Output nodes
out = GeoJsonOutput("alarms.geojson")(alarms)

# Fusion Graph
bbox = BoundingBox(48.268, 16.426, 48.27, 16.4275)
graph = Graph(inputs=[track_a, track_b], outputs=[out],
              crs="EPSG:32639", bbox=bbox, resolution=(10, 10))
graph.run()
```

```{code-cell}
:tags: [remove-input]
graph.plot_graph()
```
