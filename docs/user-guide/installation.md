# Installation

Install MuFASA and its dependencies via pip from PyPI[^mufasa-pypi]:

```bash
pip install mufasa-fusion
```

The software is licensed under Apache 2.0[^mufasa-license].

## Optional Dependencies

Install extra dependencies as follows, where `extra` is a comma-separated list chosen from below.

```bash
pip install mufasa-fusion[extra]
```

Available extras and what they enable:

`vis`
: Visual introspection tools, such as {func}`~mufasa.graph.Graph.plot_graph`
  and {class}`~mufasa.io.outputs.visualization.Visualization`

`tracking`
: Tracking nodes in {mod}`mufasa.nodes.tracking`

`dev`
: Development dependencies, including those to build these docs


## Install from Sources

Install the latest development version via pip from MuFASA's repository[^mufasa-repo]

```bash
pip install "mufasa-fusion @ git+https://github.com/mufasa-fusion/mufasa-fusion@dev"
```

[^mufasa-pypi]: `mufasa-fusion` package on Python Packaging Index, <https://pypi.org/project/mufasa-fusion>
[^mufasa-repo]: MuFASA's repository on GitHub, <https://github.com/mufasa-fusion/mufasa-fusion>
[^mufasa-license]: Apache 2.0 license file, <https://github.com/mufasa-fusion/mufasa-fusion/blob/main/LICENSE>
