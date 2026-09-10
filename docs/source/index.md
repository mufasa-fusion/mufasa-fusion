---
sd_hide_title: true
---

# MuFASA

```{raw} html
<div class="hero">
  <div class="hero-logos">
    <img class="hero-logo-mufasa" src="_static/img/mufasa_logo_light.png" alt="MuFASA" />
    <span class="hero-logo-divider"></span>
    <img class="hero-logo-ait" src="_static/img/ait_logo.jpg" alt="AIT Austrian Institute of Technology" />
  </div>
  <p class="subtitle">
    A domain-independent framework for rapid prototyping of multimodal
    sensor fusion systems. Fusion taxonomies tell you what a fusion
    process should accomplish &mdash; MuFASA gives you a direct,
    executable path to build one.
  </p>
  <div class="hero-ctas">
    <a class="btn btn-primary" href="getting-started.html">Get started</a>
    <a class="btn btn-secondary" href="https://github.com/mufasa-fusion/mufasa-fusion">View on GitHub</a>
  </div>
</div>
```

```{raw} html
<div class="path-cards">
  <a class="path-card" href="getting-started.html">
    <h3>Getting started</h3>
    <p>New to MuFASA? Install it and run your first fusion graph in a few minutes.</p>
  </a>
  <a class="path-card" href="user-guide/index.html">
    <h3>User guide</h3>
    <p>Ready to build something real? Learn the core concepts and write custom nodes.</p>
  </a>
  <a class="path-card" href="showcases.html">
    <h3>Showcases</h3>
    <p>Want to see it proven? Real deployments in border, rail, and CBRNE security.</p>
  </a>
</div>
```

## Ten lines, one working fusion graph

```{raw} html
<div class="code-graph">
<div class="ide-window">
  <div class="ide-titlebar">
    <span class="ide-dot red"></span>
    <span class="ide-dot yellow"></span>
    <span class="ide-dot green"></span>
    <span class="ide-filename">quickstart.py</span>
  </div>
```

```{code-block} python
:linenos:

from mufasa import Graph
from mufasa.io.inputs.geojson import GeoJsonInput
from mufasa.io.outputs.geojson import GeoJsonOutput
from mufasa.nodes.mapping.pom import POM
from mufasa.nodes.mapping.static import StaticMap
from mufasa.nodes.fusion.map_fusion import BayesianFusion
from mufasa.nodes.detection.threshold import Threshold

in_a = GeoJsonInput(path="sensor_a.geojson")
in_b = GeoJsonInput(path="sensor_b.geojson")
map_a = POM(decay_s=5)(in_a)
map_b = POM(decay_s=1)(in_b)
static = StaticMap(source="priors.geojson")
fused = BayesianFusion()(map_a, map_b, static)
detection = Threshold(threshold=0.7)(fused)
out = GeoJsonOutput(path="detections.geojson")(detection)

graph = Graph(inputs=[in_a, in_b], outputs=[out])
graph.run()
```

```{raw} html
</div>
<div class="graph-panel">
  <div class="graph-panel-title">Rendered graph &mdash; graph.plot_graph()</div>
```

```{raw} html
<svg width="100%" viewBox="0 0 340 500" role="img" aria-label="Rendered fusion graph for the quickstart example">
  <defs>
    <marker id="arrow-home" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="#5f5e5a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>
  <line x1="90" y1="56" x2="90" y2="94" stroke="#5f5e5a" stroke-width="0.75" marker-end="url(#arrow-home)"/>
  <line x1="250" y1="56" x2="250" y2="94" stroke="#5f5e5a" stroke-width="0.75" marker-end="url(#arrow-home)"/>
  <path d="M90 150 L90 190 L155 190 L155 208" fill="none" stroke="#5f5e5a" stroke-width="0.75" marker-end="url(#arrow-home)"/>
  <path d="M250 150 L250 190 L195 190 L195 208" fill="none" stroke="#5f5e5a" stroke-width="0.75" marker-end="url(#arrow-home)"/>
  <path d="M60 340 L60 360 L155 360 L155 378" fill="none" stroke="#5f5e5a" stroke-width="0.75" marker-end="url(#arrow-home)"/>
  <line x1="170" y1="264" x2="170" y2="302" stroke="#5f5e5a" stroke-width="0.75" marker-end="url(#arrow-home)"/>
  <line x1="170" y1="434" x2="170" y2="464" stroke="#5f5e5a" stroke-width="0.75" marker-end="url(#arrow-home)"/>

  <rect x="30" y="16" width="120" height="40" rx="8" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
  <text x="90" y="32" text-anchor="middle" font-size="11" font-weight="500" fill="#2C2C2A">GeoJSON input</text>
  <text x="90" y="46" text-anchor="middle" font-size="9" fill="#5F5E5A">sensor_a</text>

  <rect x="190" y="16" width="120" height="40" rx="8" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
  <text x="250" y="32" text-anchor="middle" font-size="11" font-weight="500" fill="#2C2C2A">GeoJSON input</text>
  <text x="250" y="46" text-anchor="middle" font-size="9" fill="#5F5E5A">sensor_b</text>

  <rect x="30" y="96" width="120" height="54" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
  <text x="90" y="116" text-anchor="middle" font-size="11" font-weight="500" fill="#04342C">POM</text>
  <text x="90" y="132" text-anchor="middle" font-size="9" fill="#0F6E56">decay_s=5</text>

  <rect x="190" y="96" width="120" height="54" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
  <text x="250" y="116" text-anchor="middle" font-size="11" font-weight="500" fill="#04342C">POM</text>
  <text x="250" y="132" text-anchor="middle" font-size="9" fill="#0F6E56">decay_s=1</text>

  <rect x="0" y="304" width="120" height="40" rx="8" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
  <text x="60" y="322" text-anchor="middle" font-size="11" font-weight="500" fill="#2C2C2A">StaticMap</text>
  <text x="60" y="336" text-anchor="middle" font-size="9" fill="#5F5E5A">priors</text>

  <rect x="110" y="210" width="120" height="54" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
  <text x="170" y="232" text-anchor="middle" font-size="11" font-weight="500" fill="#26215C">Bayesian</text>
  <text x="170" y="248" text-anchor="middle" font-size="9" fill="#534AB7">fusion</text>

  <rect x="110" y="380" width="120" height="54" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
  <text x="170" y="402" text-anchor="middle" font-size="11" font-weight="500" fill="#4A1B0C">Threshold</text>
  <text x="170" y="418" text-anchor="middle" font-size="9" fill="#993C1D">threshold=0.7</text>

  <rect x="110" y="466" width="120" height="34" rx="8" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
  <text x="170" y="487" text-anchor="middle" font-size="11" font-weight="500" fill="#2C2C2A">GeoJSON output</text>
</svg>
```

```{raw} html
  </div>
</div>
```

## Explore the node ecosystem

Every node belongs to one of six categories. Click a category to jump straight to its entries in the Node Catalog.

```{raw} html
<svg class="node-ecosystem-graph" width="100%" viewBox="0 0 680 232" role="img" aria-label="Browsable map of node categories">
  <a href="node-catalog.html#mapping">
    <rect x="40" y="40" width="180" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
    <text x="130" y="62" text-anchor="middle" font-size="14" font-weight="500" fill="#04342C">Mapping</text>
    <text x="130" y="80" text-anchor="middle" font-size="11" fill="#0F6E56">POM, HeatMap, StaticMap</text>
  </a>
  <a href="node-catalog.html#fusion">
    <rect x="250" y="40" width="180" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
    <text x="340" y="62" text-anchor="middle" font-size="14" font-weight="500" fill="#26215C">Fusion</text>
    <text x="340" y="80" text-anchor="middle" font-size="11" fill="#534AB7">Bayesian, logical and/or</text>
  </a>
  <a href="node-catalog.html#detection">
    <rect x="460" y="40" width="180" height="56" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
    <text x="550" y="62" text-anchor="middle" font-size="14" font-weight="500" fill="#4A1B0C">Detection</text>
    <text x="550" y="80" text-anchor="middle" font-size="11" fill="#993C1D">Threshold, confidence</text>
  </a>
  <a href="node-catalog.html#tracking">
    <rect x="40" y="136" width="180" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
    <text x="130" y="158" text-anchor="middle" font-size="14" font-weight="500" fill="#412402">Tracking</text>
    <text x="130" y="176" text-anchor="middle" font-size="11" fill="#854F0B">Kalman, DBSTREAM</text>
  </a>
  <a href="node-catalog.html#util">
    <rect x="250" y="136" width="180" height="56" rx="8" fill="#FBEAF0" stroke="#993556" stroke-width="0.5"/>
    <text x="340" y="158" text-anchor="middle" font-size="14" font-weight="500" fill="#4B1528">Util</text>
    <text x="340" y="176" text-anchor="middle" font-size="11" fill="#993556">Observation filter</text>
  </a>
  <a href="node-catalog.html#io">
    <rect x="460" y="136" width="180" height="56" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/>
    <text x="550" y="158" text-anchor="middle" font-size="14" font-weight="500" fill="#2C2C2A">I/O</text>
    <text x="550" y="176" text-anchor="middle" font-size="11" fill="#5F5E5A">GeoJSON, GeoTIFF, stream</text>
  </a>
</svg>
```

```{toctree}
:hidden:
:maxdepth: 2

getting-started
user-guide/index
showcases
node-catalog
api-reference
about
```
