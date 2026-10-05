:::{rst-class} mf-hidden-title
:::

# MuFASA

:::{rst-class} mf-light-only
:::

![MuFASA - Multimodal Fusion Architecture for Sensor Applications](_static/img/logo/MuFASA_MuFASA_Zusatz.svg)

:::{rst-class} mf-dark-only
:::

![MuFASA - Multimodal Fusion Architecture for Sensor Applications](_static/img/logo/MuFASA_MuFASA_Zusatz_weiss.svg)

A framework for rapid prototyping of geospatial sensor fusion pipelines.

(quickstart)=
## Installation

MuFASA is a Python package and easily installed from its [GitHub repository][mufasa-repo] with pip:

```bash
pip install "mufasa[vis] @ https://github.com/mufasa-fusion/mufasa-fusion"
```

It is licensed under [Apache 2.0][mufasa-license].

[mufasa-repo]: https://github.com/mufasa-fusion/mufasa-fusion
[mufasa-license]: https://github.com/mufasa-fusion/mufasa-fusion/blob/main/LICENSE

## Usage

Build a Fusion Graph in a few lines of Python code.

::::{container} mf-side-by-side

```{code-block} python
:caption: A simple Fusion Graph in Python code

from mufasa import Graph
from mufasa.io.inputs import GeoJsonInput
from mufasa.io.outputs import GeoJsonOutput
from mufasa.nodes import StaticMap, POM, \
    BayesianFusion, Threshold

track_a = GeoJsonInput("sensor_a.geojson")
track_b = GeoJsonInput("sensor_b.geojson")
static = StaticMap("priors.geojson")

pom_a = POM(decay_s=5)(track_a)
pom_b = POM(decay_s=1)(track_b)
fused = BayesianFusion()(
    pom_a, pom_b, static
)
alarms = Threshold(threshold=0.7)(fused)
out = GeoJsonOutput()(alarms)

graph = Graph(
    inputs=[track_a, track_b],
    outputs=[out],
)
graph.run()
```

```{digraph} fusion_graph
:caption: An example Fusion Graph visualized
:align: center

graph [class="mf-fusion-graph"]
node [shape=plain]

track_a [class="geojson-to-obs", label=<<table cellborder="0">
    <tr><td><b>GeoJsonInput</b></td></tr>
    <tr><td>"sensor_a.geojson"</td></tr>
</table>>]

track_b [label=<<table cellborder="0">
    <tr><td><b>GeoJsonInput</b></td></tr>
    <tr><td>"sensor_b.geojson"</td></tr>
</table>>]

pom_a [label=<<table cellborder="0">
    <tr><td><b>POM</b></td></tr>
    <tr><td>decay_s = 5</td></tr>
</table>>]

pom_b [label=<<table cellborder="0">
    <tr><td><b>POM</b></td></tr>
    <tr><td>decay_s = 1</td></tr>
</table>>]

static [label=<<table cellborder="0">
    <tr><td><b>StaticMap</b></td></tr>
    <tr><td>"priors.geojson"</td></tr>
</table>>]

fused [label=<<table cellborder="0">
    <tr><td><b>BayesianFusion</b></td></tr>
</table>>]

alarms [label=<<table cellborder="0">
    <tr><td><b>Threshold</b></td></tr>
    <tr><td>threshold = 0.7</td></tr>
</table>>]

out [label=<<table cellborder="0">
    <tr><td><b>GeoJsonOutput</b></td></tr>
</table>>]

track_a -> pom_a -> fused
track_b -> pom_b -> fused
static -> fused -> alarms -> out
```
::::

```{toctree}
:hidden:
:maxdepth: 2

user-guide/index
showcases/index
catalog
api/index
about
```
