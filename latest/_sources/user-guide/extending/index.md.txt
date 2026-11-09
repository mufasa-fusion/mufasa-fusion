# Extending MuFASA

Extending MuFASA allows you to

- Connect to more data formats and external systems
- Include other processing algorithms

Both are achieved by implementing your own subclass of {class}`~mufasa.node.Node`.
Before you do, check whether you need a new node at all: often a few lines of preparation code
and a built-in node achieve the same, which is in the spirit of rapid prototyping.
A dedicated node pays off when you want to reuse or share it, or save and load graphs that use it.

[Writing a Node](nodes.md)
: The basics of every node, shown with small examples for processing Locations and Maps, input and output nodes,
  and saving and loading graphs.

[Connecting Custom Data Sources](sources.md)
: Which approach fits your data source, and how to write input nodes for live data from pull and push clients.

```{toctree}
:hidden:

nodes
sources
```

