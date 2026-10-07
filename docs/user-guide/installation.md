# Installation

Install MuFASA and its dependencies via pip:

```bash
pip install "mufasa @ git+https://github.com/mufasa-fusion/mufasa-fusion"
```

## Optional dependencies

Install extra dependencies as follows, where `extra` is a comma-separated list chosen from below.

```bash
pip install "mufasa[extra] @ git+https://github.com/mufasa-fusion/mufasa-fusion"
```

Available extras and what they enable:

`vis`
: Visual introspection tools, such as {func}`~mufasa.graph.Graph.plot_graph`
  and {class}`~mufasa.io.outputs.visualization.Visualization`

`tracking`
: Tracking nodes in {mod}`mufasa.nodes.tracking`

`dev`
: Development dependencies, including those to build these docs
