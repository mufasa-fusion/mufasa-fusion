# User Guide

This guide explains how to build multi-sensor fusion applications with MuFASA, from installing the package to running a Fusion Graph on live sensor data. If you are new to MuFASA, read from top to bottom. If you already know the basics, jump straight to the topic you need.

[Installation](installation.md)
: Install `mufasa-fusion` from PyPI and add the optional extras you need.

[Design principles](design-principles.md)
: The three ideas behind MuFASA and where it sits between your sensors and your decision support.

[Concepts](concepts.md)
: The building blocks of a Fusion Graph: detections, maps, input and output nodes and processing nodes.

[Tips and Tricks](tips-and-tricks.md)
: Practical recipes for inspecting and visualising data, working with GeoPandas and saving graphs as JSON.

[Extending MuFASA](extending/index.md)
: Write your own nodes to connect new data sources or add your own processing algorithms.

[Going Live](going-live/index.md)
: Run the same Fusion Graph on live data from MQTT or ROS 2 instead of recordings.

```{toctree}
:hidden:

installation
design-principles
concepts
tips-and-tricks
extending/index
going-live/index
```
