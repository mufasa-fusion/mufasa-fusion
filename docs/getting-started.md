---
file_format: mystnb
---

```{code-cell}
:tags: [remove-cell]
import os
os.chdir("_data")
```

# Getting started

## Install MuFASA

MuFASA is a Python package and easily installed from its [GitHub repository][mufasa-repo] with pip:

```bash
pip install "mufasa[vis] @ git+https://github.com/mufasa-fusion/mufasa-fusion"
```

## The Fusion Recipe

Follow these simple steps to define and run any fusion architecture in MuFASA.
It will also briefly introduce you to the core building blocks by an example.

### Load Input

For example, use a {class}`~mufasa.io.inputs.geojson.GeoJsonInput` node
to load data from [`mappings.geojson`](/_data/mappings.geojson).

```{code-cell}
from mufasa.io.inputs import GeoJsonInput

inp = GeoJsonInput("mappings.geojson")
```

### Compose Nodes

Pick some fusion nodes and compose them to define your desired fusion architecture.
In this example, we use a Probability Occupancy Map ({class}`~mufasa.nodes.mapping.pom.POM`) node
that we connect to the input defined above.

```{code-cell}
from mufasa.nodes.mapping import POM

pom = POM(decay_s=5)(inp)
```

### Define Output

Here, we send the POM to a {class}`~mufasa.io.outputs.visualization.Visualization`.

```{code-cell}
from mufasa.io.outputs import Visualization

vis = Visualization(snapshot_interval_s=0)(pom)
```

### Assemble Graph

Finally, assemble the Fusion Graph. The {class}`~mufasa.graph.Graph` needs to know the IO boundary nodes
as well as the bounding box and map resolution for the POM and the coordinate reference system for calculations.

:::{rst-class} mf-side-by-side
:::

```{code-cell}
from mufasa import BoundingBox, Graph

bbox = BoundingBox(
    min_x=16.426371764128696,
    min_y=48.26746099712581,
    max_x=16.42828135471482,
    max_y=48.26995824720053,
)
graph = Graph(
    inputs=[inp],
    outputs=[vis],
    crs="EPSG:32633",
    bbox=bbox,
    resolution=(2, 2),
)

graph.plot_graph()
```

### Execute Fusion

Now, everything is set up to run the sensor fusion:

```{code-cell}
graph.run()
```

### Inspect Results

Let's have a look at the last snapshot that came from the POM:

```{code-cell}
vis.show("pom_0")
```

## Next Steps

:::{seealso}
- {doc}`user-guide/index` for an introduction to the framework and its API
- {doc}`catalog` for a list of available fusion nodes to build your own graphs
- {doc}`showcases/index` for realized fusion architectures and use-cases to draw inspiration from
:::

[mufasa-repo]: https://github.com/mufasa-fusion/mufasa-fusion
[mufasa-license]: https://github.com/mufasa-fusion/mufasa-fusion/blob/main/LICENSE
