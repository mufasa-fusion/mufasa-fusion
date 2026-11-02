# Extending MuFASA

Extending MuFASA allows you to

- Connect to more data formats and external systems
- Include other processing algorithms

Both is achieved by implementing your own subclass of {class}`~mufasa.node.Node` and optionally also a data type.
The details are explained in the following guides:

```{toctree}
:maxdepth: 1

sources
```

:::{admonition} Coming Soon
:class: admonition-todo
Guides for custom processing and output nodes as well as new data models.

For now, consult {doc}`sources`, MuFASA's README and source code[^repo],
and existing pull requests[^soda-citron] for inspiration.
:::

[^repo]: MuFASA's repository on GitHub, <https://github.com/mufasa-fusion/mufasa-fusion>
[^soda-citron]: SODA-CitrON Pull Request, MuFASA's repository on GitHub,
<https://github.com/mufasa-fusion/mufasa-fusion/pull/4>
