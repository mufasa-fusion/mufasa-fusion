---
layout: simple
content_max_width: 72rem
---

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

## The Fusion Graph

MuFASA interprets a fusion system as a Fusion Graph: a directed acyclic graph that starts at Input nodes
and ends at Output nodes. You compose it functionally by calling each node on its inputs, and nodes connect
wherever their data types match. Learn more about the concept in the {doc}`user-guide/index`.

```{fusion-graph}
:show-code:
:caption: A simple Fusion Graph in Python code

from mufasa import Graph
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
graph = Graph(inputs=[track_a, track_b], outputs=[out])
graph.run()
```

## Find your way through the docs

::::{container} mf-doc-paths

:::{container}
**New to MuFASA**

{doc}`getting-started/index` walks you through installing MuFASA and running your first Fusion Graph.
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

getting-started/index
user-guide/index
showcases/index
catalog
api/index
about
```
