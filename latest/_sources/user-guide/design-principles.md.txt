# Design principles

MuFASA is built on three principles. The colors on this page mark where each one shows up
in the architecture.

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

## In short

::::{container} mf-fit-check

:::{container} mf-fit-yes
**MuFASA is the right tool for you if you**

- already have detections (positions or georeferenced maps) and want to build a fusion system on top of them
- want to quickly compare different fusion configurations
- want to move from recorded data to live data without rewriting your graph
- enjoy digging into your data :)
:::

::::
