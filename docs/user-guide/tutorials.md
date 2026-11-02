---
file_format: mystnb
---

```{code-cell}
:tags: [remove-cell]
import os.path
os.chdir(os.path.join("..", "_data"))
```

# Tips and Tricks

## Data Inspection

The most basic Fusion Graph possible doesn't do any processing at all.
It consists of one input node and one output node only.
Here, we will use such a graph to inspect its data flow.

### Input

With recorded data sources, you can leverage their input nodes
to inspect the data loaded into MuFASA's internal representation:

```{code-cell}
from mufasa.io.inputs import GeoJsonInput

src = GeoJsonInput("sensor_b.geojson")
src.items()
```

### Infer Bounding Box

This allows you to infer the bounding box from your input data:

```{code-cell}
from mufasa import BoundingBox
import numpy as np
import shapely

src_bounds = np.array([shapely.bounds(i.geometry) for i in src.items()])

min_x = src_bounds[:, 0].min().item()
min_y = src_bounds[:, 1].min().item()
max_x = src_bounds[:, 2].max().item()
max_y = src_bounds[:, 3].max().item()
x_tol = (max_x - min_x) * .1
y_tol = (max_y - min_y) * .1

bbox = BoundingBox(
    min_x - x_tol,
    min_y - y_tol,
    max_x + x_tol,
    max_y + y_tol,
)
bbox
```

### Output

Use a {class}`~mufasa.io.outputs.python_object.LocationOutput` node
(or its {class}`~mufasa.io.outputs.python_object.MapOutput` equivalent)
to collect the data output by its predecessors into a Python list.

```{code-cell}
from mufasa.io.outputs import LocationOutput

out = LocationOutput()(src)

from mufasa import Graph
from mufasa.graph import _suggest_utm_crs

graph = Graph(
    inputs=[src],
    outputs=[out],
    bbox=bbox,
    resolution=(1, 1),
    crs=_suggest_utm_crs(bbox),
)

graph.run()
out.result
```

Here, this verifies that all input data had been passed on.

## Visualization

MuFASA provides two built-in visualizations: one for plotting fusion architectures
and the other for showing data on a map.

:::{important}
This requires MuFASA to be installed with `vis` extra dependencies.
:::

Redefine the {class}`~mufasa.io.inputs.geojson.GeoJsonInput` node from above
and connect it to a {class}`~mufasa.io.outputs.visualization.Visualization` node.
The input from the previous section is already connected in a Fusion Graph and unfortunately can't be reused.

```{code-cell}
from mufasa.io.outputs import Visualization

src = GeoJsonInput("sensor_b.geojson")
vis = Visualization()(src)

graph = Graph(
    inputs=[src],
    outputs=[vis],
    bbox=bbox,
    resolution=(1, 1),
    crs=_suggest_utm_crs(bbox),
)
```

Note that we need to set a `bbox` and `resolution` this time
-- although the graph isn't processing any {class}`~mufasa.map.Map`.
This is due to the fact that the Visualisation node also accepts Maps as input.
This bounding box will also bound the visualization.
The CRS is optional, but it will enhance the visualization with map tiles.

:::{todo}
Shouldn't the typing mechanism be smart enough to check that no map is produced?
:::

You can now visually inspect the graph structure:

```{code-cell}
graph.plot_graph()
```

And finally, after running the fusion, {func}`~mufasa.io.outputs.visualization.Visualization.show`
the latest snapshot of data fed to the visualization node over its first input (thus the index `0`):

```{code-cell}
graph.run()
vis.show(0)
```

There's also an {func}`~mufasa.io.outputs.visualization.Visualization.animate` method
for data with different timestamps.

:::{todo}
Fix the map tiles issue!
:::

## GeoPandas Integration

MuFASA integrates nicely with Pandas[^Pandas] and GeoPandas[^GeoPandas].
In fact, GeoPandas is used in the Visualization node behind the scenes.
Here are some tips and tricks on how to utilize (Geo)Pandas with MuFASA.

:::{admonition} Installation
:class: tip

If you haven't installed MuFASA with `vis` extra dependencies, then you need to install GeoPandas separately:

```bash
pip install geopandas
```
:::

```{code-cell}
import geopandas
```

### Convert to `DataFrame`s

Pandas and GeoPandas are capable of loading lists of Python Dataclasses into their `DataFrame`s.
Thus, they understand MuFASA's {class}`~mufasa.location.Location`s.

```{code-cell}
src_df = geopandas.GeoDataFrame(src.items())
src_df
```

```{code-cell}
out_df = geopandas.GeoDataFrame(out.result)
out_df
```

You might also want to unwrap the properties into separate columns:

```{code-cell}
import numpy as np
import pandas

src_props_df = src_df["properties"].apply(pandas.Series)
src_total_df = pandas.concat([src_df, src_props_df], axis="columns")
src_total_df
```

### Bounding Boxes

Tired of defining them manually?

```{code-cell}
bounds = src_df.bounds
bbox = BoundingBox(
    bounds.minx.min().item(),
    bounds.miny.min().item(),
    bounds.maxx.max().item(),
    bounds.maxy.max().item(),
)
bbox
```

### Visualizations

To get more customization options, you can create plots via GeoPandas manually.

```{code-cell}
# Fill missing values so we have something to show
src_total_df.fillna({"confidence": .25, "headquarters": False}, inplace=True)
src_total_df
```

```{code-cell}
src_total_df.plot("headquarters", markersize=100*src_total_df["confidence"], legend=True);
```

```{code-cell}
src_total_df.boxplot(column="confidence", by="headquarters");
```

(dict-config)=
## JSON Serialization

You might have noticed {func}`Node.get_config() <mufasa.node.Node.get_config>`.
It simply returns a node's parametrization to a JSON-serializable dict.

```{code-cell}
src.get_config()
```

There's also {func}`Graph.to_config() <mufasa.graph.Graph.to_config>` to export an entire Fusion Graph.

```{code-cell}
conf = graph.to_config()
conf
```

Reconstruct it later with {func}`Graph.from_config() <mufasa.graph.Graph.from_config>`.

```{code-cell}
new_graph = Graph.from_config(conf)
new_graph.plot_graph()
```

For loading to work, every node used needs to be registered with the {attr}`~mufasa.registry.NODE_REGISTRY`.
Keep that (and overwriting {func}`mufasa.node.Node.get_config`) in mind when extending MuFASA with new nodes!

```{code-cell}
from mufasa.registry import NODE_REGISTRY

NODE_REGISTRY
```

[^Pandas]: Pandas, see <https://pandas.pydata.org>
[^GeoPandas]: GeoPandas, see <https://geopandas.org>
