---
file_format: mystnb
layout: simple
content_max_width: 72rem
---

```{code-cell}
:tags: [remove-cell]
# To give fusion graphs access to the hidden data folder
import os
os.chdir("_data")
```

:::{rst-class} mf-hidden-title
:::

# MuFASA

:::{rst-class} mf-light-only
:::

![MuFASA - Multimodal Fusion Architecture for Sensor Applications](_static/img/logo/MuFASA_MuFASA_Zusatz.svg)

:::{rst-class} mf-dark-only
:::

![MuFASA - Multimodal Fusion Architecture for Sensor Applications](_static/img/logo/MuFASA_MuFASA_Zusatz_weiss.svg)

A framework for rapid prototyping of geospatial sensor fusion systems. MuFASA turns the design of a multimodal fusion system into an explicit, executable graph.

(quickstart)=
## The Fusion Graph

MuFASA interprets a fusion system as a Fusion Graph: a directed acyclic graph that starts at Input nodes
and ends at Output nodes. You compose it functionally by calling each node on its inputs, and nodes connect
wherever their data types match. Learn more about the concept in the {doc}`user-guide/index`.

```{code-cell}
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

## Find your way through the docs

::::{container} mf-doc-paths

:::{container}
**New to MuFASA**

{doc}`getting-started` walks you through installing MuFASA and running your first Fusion Graph.
The {doc}`user-guide/index` explains the core concepts: Locations, Maps, Nodes and Graphs.
:::

:::{container}
**Evaluating for your domain**

The {doc}`showcases/index` show MuFASA in controlled real-world environments.
The {doc}`catalog` lists the nodes and data types you can build with.
:::

:::{container}
**Building your system**

The {doc}`user-guide/index` covers custom nodes and live deployment.
The {doc}`api/index` documents every class and parameter.
:::

::::

```{toctree}
:hidden:
:maxdepth: 2

getting-started
user-guide/index
showcases/index
catalog
api/index
about
```
