<div align="center">
  <img src="docs/assets/MuFASA_logo.png" alt="MuFASA" height="80" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/assets/ait_logo.jpg" alt="AIT Austrian Institute of Technology" height="60" />
</div>

<br>

# MuFASA — Multimodal Fusion Architecture for Sensor Applications

MuFASA is a framework for rapid prototyping of geospatial sensor fusion pipelines. You don't need deep knowledge of fusion methods or sensor modalities to get started — wire nodes together with Python, run them on recorded data or live streams, and swap components without touching the rest of the pipeline. 

---

## Installation

```bash
pip install mufasa                      # core
pip install "mufasa[tracking]"          # + KalmanTracker, DBSTREAMClusterer
pip install "mufasa[vis]"               # + plot_map, animate_maps, plot_locations
pip install "mufasa[tracking,vis]"      # everything
```

Requires Python ≥ 3.10.

---

## Core concepts

| Concept | Description |
|---------|-------------|
| **Location** | A geospatial object: geometry, optional timestamp, and free-form properties. `Observation` extends `Location` with a `confidence` field and is the standard type for sensor detections. |
| **Map** | A raster grid over a geographic area, backed by a NumPy array with a rasterio affine transform and CRS. |
| **Node** | A processing unit that accepts Locations and/or Maps, transforms them, and passes results downstream. |
| **Graph** | A validated DAG of nodes. Checks wiring at construction time and distributes spatial configuration to every node. |

---

## Quick start

```python
from mufasa import BoundingBox, Graph
from mufasa.io.inputs.geojson import GeoJsonInput
from mufasa.io.outputs.python_object import LocationOutput
from mufasa.nodes.mapping import POM
from mufasa.nodes.fusion import BayesianFusion
from mufasa.nodes.detection import ConfidenceThreshold

# --- Define inputs ---
track_a = GeoJsonInput(path="sensor_a.geojson")
track_b = GeoJsonInput(path="sensor_b.geojson")

# --- Build pipeline ---
pom_a  = POM(decay_s=300)(track_a)
pom_b  = POM(decay_s=300)(track_b)
fused  = BayesianFusion()(pom_a, pom_b)
alarms = ConfidenceThreshold(threshold=0.7)(fused)
out    = LocationOutput()(alarms)

# --- Assemble and run ---
graph = Graph(
    inputs=[track_a, track_b],
    outputs=[out],
    crs="EPSG:32633",
    bbox=BoundingBox(14.0, 47.0, 14.2, 47.2),
    resolution=(10.0, 10.0),
)
graph.run()

detections = out.result  # list[Observation]
```

Changing a parameter between runs is a plain attribute assignment — no API needed:

```python
# tighten the alarm threshold after inspection
alarms.threshold = 0.85
graph.run()
```

---

## Built-in nodes

### Mapping — `mufasa.nodes.mapping`

| Class | Input → Output | Description |
|-------|----------------|-------------|
| `POM` | `Observation → BayesianMap` | Probability Occupancy Map: Bayesian log-odds accumulation with exponential temporal decay. |
| `StaticMap` | `→ BayesianMap` | Source node: loads a fixed prior from a GeoJSON file at startup and contributes to fusion without any runtime updates. |

### Fusion — `mufasa.nodes.fusion`

| Class | Input → Output | Description |
|-------|----------------|-------------|
| `BayesianFusion` | `BayesianMap… → BayesianMap` | Sums log-odds across all inputs (assumes conditional independence). |
| `LogicalAnd` | `BayesianMap… → BayesianMap` | Element-wise minimum in log-odds space. |
| `LogicalOr` | `BayesianMap… → BayesianMap` | Element-wise maximum in log-odds space. |

### Detection — `mufasa.nodes.detection`

| Class | Input → Output | Description |
|-------|----------------|-------------|
| `Threshold` | `Map → Location` | Connected-component labelling on pixels at or above a value threshold; emits one `Location` per component with `mean_value` in properties. |
| `ConfidenceThreshold` | `BayesianMap → Observation` | Like `Threshold` but operates on probabilities (0–1); emits one `Observation` per component with `confidence` = mean probability. |

### Tracking — `mufasa.nodes.tracking`

| Class | Input → Output | Description |
|-------|----------------|-------------|
| `KalmanTracker` | `Location → Observation` | Multi-target Kalman filter (Stone Soup backend); buffers observations into fixed-length windows before each predict–update cycle. |
| `DBSTREAMClusterer` | `Location → Location` | Online density-based clustering (DBSTREAM via River); emits one `Location` per cluster centroid. |

### Utility — `mufasa.nodes.util`

| Class | Input → Output | Description |
|-------|----------------|-------------|
| `ObservationFilter` | `Observation → Observation` | Filters observations by confidence threshold, time window, and/or property regex patterns; all criteria are AND-combined. |

### I/O — `mufasa.io`

| Class | Role |
|-------|------|
| `GeoJsonInput` | Load Locations or Observations from a GeoJSON file; emits `Observation` if a `confidence` column is present, `Location` otherwise. |
| `GeoTiffInput` | Load a raster map from a GeoTIFF file. |
| `GeoJsonOutput` | Write collected Locations/Observations to a GeoJSON file (reprojected to WGS84). |
| `GeoTiffOutput` | Write map snapshots to GeoTIFF. |
| `LocationOutput` | Collect Locations/Observations in memory (`output.result`). |
| `MapOutput` | Collect periodic map snapshots in memory. |
| `Visualization` | Debug output that collects both Map snapshots and Locations; inspect with `viz.show(index)` or animate with `viz.animate(index)` after the run. |

---

## How to write a new node

Every node subclasses `Node` and declares three things: what types it accepts, what type it emits, and how to serialise its constructor arguments.

### Observation-to-observation node

The simplest pattern: receive one `Observation`, push one (or more) downstream.

```python
from mufasa.node import Node
from mufasa.location import Observation

class ConfidenceBoost(Node):
    """Multiplies every observation's confidence by a fixed factor."""

    _input_types = [Observation]   # accepts Observation (and any subclass)
    _output_type = Observation     # emits Observation

    def __init__(self, factor: float = 1.2) -> None:
        super().__init__()
        self.factor = factor

    def process(self, obs: Observation) -> None:
        boosted = Observation(
            geometry=obs.geometry,
            timestamp=obs.timestamp,
            confidence=min(obs.confidence * self.factor, 1.0),
        )
        for successor in self._successors:
            successor.process(boosted)

    def get_config(self) -> dict:
        return {"factor": self.factor}
```

### Map-consuming node

Map nodes are called with no arguments — they read from `self._predecessors[n].map` and call `self._trigger_successors()` when done.

```python
from mufasa.node import Node
from mufasa.map import Map
import numpy as np

class MapClipper(Node):
    """Clips all map values to a maximum."""

    _input_types = [Map]
    _output_type = Map

    def __init__(self, cap: float = 0.9) -> None:
        super().__init__()
        self.cap = cap
        self._map: Map | None = None

    def configure(self, crs, bbox, resolution) -> None:
        # Called by Graph at construction time; initialise spatial state here.
        self._map = Map.from_bounds(bbox, resolution, crs)

    def process(self) -> None:
        src = self._predecessors[0].map
        np.clip(src.data, a_min=None, a_max=self.cap, out=self._map.data)
        self._map.timestamp = src.timestamp
        self._trigger_successors()

    @property
    def map(self) -> Map:
        return self._map

    def reset(self) -> None:
        if self._map is not None:
            self._map.data[:] = 0.0

    def get_config(self) -> dict:
        return {"cap": self.cap}
```

### Stateful node (buffering + end-of-stream flush)

Override `flush()` and `reset()` when your node accumulates data across calls. `flush()` is called by the framework after all inputs are exhausted; `reset()` is called between pipeline runs.

```python
from mufasa.node import Node
from mufasa.location import Observation

class BatchEmitter(Node):
    """Holds observations until a batch of `n` is ready, then emits them all."""

    _input_types = [Observation]
    _output_type = Observation

    def __init__(self, n: int = 10) -> None:
        super().__init__()
        self.n = n
        self._buffer: list[Observation] = []

    def process(self, obs: Observation) -> None:
        self._buffer.append(obs)
        if len(self._buffer) >= self.n:
            self._flush()

    def flush(self) -> None:
        """Called by the framework at end of stream."""
        if self._buffer:
            self._flush()

    def reset(self) -> None:
        self._buffer.clear()

    def _flush(self) -> None:
        for obs in self._buffer:
            for successor in self._successors:
                successor.process(obs)
        self._buffer.clear()

    def get_config(self) -> dict:
        return {"n": self.n}
```

### Register for save/load

To make a node serialisable via `Graph.to_config()` / `Graph.from_config()`, add one line to [src/registry.py](src/registry.py):

```python
from mypackage.nodes import ConfidenceBoost

NODE_REGISTRY["ConfidenceBoost"] = ConfidenceBoost
```

The key must match `type(node).__name__` exactly.

### Checklist

| | Requirement |
|---|---|
| ☐ | `_input_types` declared (`[]` for input nodes) |
| ☐ | `_output_type` declared (`None` for output nodes) |
| ☐ | `process()` implemented with the correct signature |
| ☐ | `get_config()` returns all constructor arguments as a JSON-serialisable dict (optional)|
| ☐ | `configure()` overridden if spatial setup is needed (optional)|
| ☐ | `reset()` overridden if the node holds runtime state (optional)|
| ☐ | `flush()` overridden if the node buffers data across calls (optional)|
| ☐ | Registered in `NODE_REGISTRY` if serialisation is needed (optional)|

---

## Development

```bash
# install with dev dependencies
pip install -e ".[dev]"

# run the test suite
pytest

# run with coverage
pytest --cov=mufasa
```
