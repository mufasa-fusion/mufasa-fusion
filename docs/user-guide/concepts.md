# Concepts

MuFASA represents each sensor fusion system as a directed, acyclic graph -- the Fusion Graph.
Its internal nodes define processing operations. Edges encode information flow. 
Input and output nodes define the boundary of a Fusion Graph, 
while at the same time functioning as connectors to external data sources or sinks respectively.

## The Fusion Graph

A {class}`~mufasa.graph.Graph` object represents a Fusion Graph,
binding all nodes reachable from its {attr}`inputs` to {attr}`outputs` together.
It is responsible for type compatibility checking and orchestrates the execution of the fusion system
via its {func}`~mufasa.graph.Graph.run` method. It also distributes global configuration – {attr}`crs`,
{attr}`bounding box <bbox>` and map raster {attr}`resolution` – to every node.

```python

from mufasa.graph import Graph

graph = Graph(
    inputs=[...],
    outputs=[...],
    crs="",
)

graph.run()
```

## Data Flow

All information flowing within a Fusion Graph is of one of two fundamental data types,
{class}`~mufasa.location.Location` and {class}`~mufasa.map.Map`, or any more specific one derived from them.
Every edge adheres to a single data type that is determined by the nodes it connects.
Every node specifies the set of types it accepts and the single one it produces.
Only compatible nodes might be wired together.

:::{seealso}
The {ref}`data-models-catalog` catalog for a complete list of builtin data models
:::

## IO Boundary Layer

## Processing Nodes
