---
file_format: mystnb
---
# Tutorials

```{code-cell}
:tags: [remove-cell]

import sys
import os

sys.path.append(os.path.join("..", "..", "src"))
```

(minimal-example)=
## Minimal Example

The most basic Fusion Graph possible doesn't do any processing at all.
It consists of one input node and one output node only.

### Load Input

To get started with sensor fusion, we'll need sensor data. MuFASA isn't operating on raw sensor values though,
rather it consumes already processed detections. It ships with a variety of input nodes to load them
from standardized formats.

We start by loading data from a GeoJSON[^GeoJSON] Feature Collection in [`sensor_a.geojson`](sensor_a.geojson)
with a {class}`~mufasa.io.inputs.geojson.GeoJsonInput` node.

```{code-cell}
from mufasa.io.inputs import GeoJsonInput

src_a = GeoJsonInput("sensor_a.geojson")
```

You can inspect the data loaded into MuFASA's internal representation:

```{code-cell}
src_a.items()
```

:::{hint}
Any feature with a `confidence` in its `properties` gets loaded as an {class}`~mufasa.location.Observation`,
a probabilistic version of {class}`~mufasa.location.Location`.
:::

### Define Output

Next, we'll add an output node to build the simplest Fusion Graph possible.
We choose a {class}`~mufasa.io.outputs.python_object.LocationOutput` node here for demonstration purposes.
It simply collects its inputs into a Python list.

```{code-cell}
from mufasa.io.outputs import LocationOutput

out = LocationOutput()(src_a)
```

At the same time, we connected `src_a` to feed into our new `out` node by calling it with the respective input node(s).

### Execute Fusion

Finally, we assemble the Fusion Graph. The {class}`~mufasa.graph.Graph` needs to know the IO boundary nodes.

```{code-cell}
from mufasa import Graph

graph = Graph(inputs=[src_a], outputs=[out])
```

You can ignore the warning shown for now since our graph doesn't involve any real processing.

Now, everything is set up to run our sensor fusion:

```{code-cell}
graph.run()
```

Let's inspect the results via our output node to verify all input data had been passed on.

```{code-cell}
out.result
```

## Visualization

Based on the {ref}`minimal-example`, we switch the output to showcase MuFASA's visual inspection capabilities
and the ease of evolving Fusion Graphs by adapting nodes.

:::{important}
This requires MuFASA to be installed with `vis` extra dependencies.
:::

### Define Graph

We redefine the {class}`~mufasa.io.inputs.geojson.GeoJsonInput` node from above
-- the old one is already connected in a Fusion Graph and unfortunately can't be reused.

```{code-cell}
src_a = GeoJsonInput("sensor_a.geojson")
```

This time, we connect it to a {class}`~mufasa.io.outputs.visualization.Visualization` node.

```{code-cell}
from mufasa.io.outputs import Visualization

vis_out = Visualization()(src_a)
```

And wrap it in a new Fusion Graph.

Note that we need to set a `bbox` and `resolution` this time
-- although the graph isn't processing any {class}`~mufasa.map.Map`.
This is due to the fact that the Visualisation node also accepts Maps as input.
This bounding box will also bound the visualization.
The CRS is optional, but it will enhance the visualization with map tiles.

:::{admonition} TODO
Shouldn't the typing mechanism be smart enough to check that no map is produced?
:::

```{code-cell}
from mufasa import BoundingBox
from mufasa.graph import _suggest_utm_crs

# Infer bounding box from source locations
src_a_geoms = [i.geometry for i in src_a.items()]
xs = [i.x for i in src_a_geoms]
ys = [i.y for i in src_a_geoms]

min_x = min(xs)
max_x = max(xs)
min_y = min(ys)
max_y = max(ys)
x_tol = (max_x - min_x) * .1
y_tol = (max_y - min_y) * .1

bbox = BoundingBox(
    min_x - x_tol,
    min_y - y_tol,
    max_x + x_tol,
    max_y + y_tol,
)

graph = Graph(
    inputs=[src_a],
    outputs=[vis_out],
    crs=_suggest_utm_crs(bbox),
    bbox=bbox,
    resolution=(1, 1),
)
```

### Visualize Results

You can now visually inspect the graph structure.

```{code-cell}
graph.plot_graph()
```

And finally, after running the fusion, visualize the latest snapshot of data:

```{code-cell}
graph.run()
vis_out.show(0)
```

There's also an {func}`~mufasa.io.outputs.visualization.Visualization.animate` method
for data with different timestamps.

:::{admonition} TODO
Fix the map tiles issue!
:::

## GeoPandas integration

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
src_a_df = geopandas.GeoDataFrame(src_a.items())
src_a_df
```

```{code-cell}
out_df = geopandas.GeoDataFrame(out.result)
out_df
```

You might also want to unwrap the properties into separate columns:

```{code-cell}
import numpy as np
import pandas

src_a_props_df = src_a_df["properties"].apply(pandas.Series)
src_a_total_df = pandas.concat([src_a_df, src_a_props_df], axis="columns")
src_a_total_df
```

### Bounding Boxes

Tired of defining them manually?

```{code-cell}
bounds = src_a_df.bounds
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
src_a_total_df.fillna({"confidence": .25, "headquarters": False}, inplace=True)
src_a_total_df
```

```{code-cell}
src_a_total_df.plot("headquarters", markersize=100*src_a_total_df["confidence"], legend=True);
```

```{code-cell}
src_a_total_df.boxplot(column="confidence", by="headquarters");
```

[^GeoJSON]: GeoJSON, see <https://geojson.org>
[^Pandas]: Pandas, see <https://pandas.pydata.org>
[^GeoPandas]: GeoPandas, see <https://geopandas.org>
