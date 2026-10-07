# Design principles

MuFASA is built on three principles. The colors on this page mark where each one shows up,
in the architecture and in a complete example.

::::{container} mf-principles-legend

:::{container} mf-legend-io
**Detection level**

MuFASA works on detections, not raw signals. Only the Input and Output nodes deal with files
and formats. Everything in between works on {class}`~mufasa.location.Location`s and {class}`~mufasa.map.Map`s.
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

::::{container} mf-side-by-side mf-annotated

```{code-block} python
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

```{digraph} design_principles_graph
:caption: The same Fusion Graph, colored by role
:align: center

graph [class="mf-fusion-graph", nodesep=0.15]
node [shape=plain, fontname="Arial", fontsize=12]

track_a [class="mf-io", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>GeoJsonInput</b></td></tr>
    <tr><td>"sensor_a.geojson"</td></tr>
</table>>]

track_b [class="mf-io", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>GeoJsonInput</b></td></tr>
    <tr><td>"sensor_b.geojson"</td></tr>
</table>>]

static [class="mf-io", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>StaticMap</b></td></tr>
    <tr><td>"priors.geojson"</td></tr>
</table>>]

pom_a [class="mf-proc", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>POM</b></td></tr>
    <tr><td>decay_s = 5</td></tr>
</table>>]

pom_b [class="mf-proc", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>POM</b></td></tr>
    <tr><td>decay_s = 1</td></tr>
</table>>]

fused [class="mf-proc", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>BayesianFusion</b></td></tr>
</table>>]

alarms [class="mf-proc", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>Threshold</b></td></tr>
    <tr><td>threshold = 0.7</td></tr>
</table>>]

out [class="mf-io", label=<<table cellborder="0" cellpadding="4">
    <tr><td><b>GeoJsonOutput</b></td></tr>
    <tr><td>"alarms.geojson"</td></tr>
</table>>]

track_a -> pom_a -> fused
track_b -> pom_b -> fused
static -> fused -> alarms -> out
```

::::
