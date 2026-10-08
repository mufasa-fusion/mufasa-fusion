---
file_format: mystnb
---

# Railway security

<span class="mf-status mf-status-tested">Field-tested</span>

**Use cases:** <span class="mf-tag">Trespassing</span> <span class="mf-tag">Sabotage</span>
<span class="mf-tag">Vandalism</span>

Detection along railway corridors, by day and at night.

## At a glance

```{figure} img/railway-sensor-setup.jpg
:alt: Aerial view of the rail yard with the sensor fields of view and the region of interest

Sensor setup of the trial: thermal cameras (green), acoustic sensors (blue), radar (orange) and the
150 m × 30 m region of interest (black). From Hubner et al., *Sensors* 2024, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
```

```{list-table}
:widths: 1 3

* - **Objects of interest**
  - Persons, objects placed on the track, vandalism such as breaking glass or spray-can use
* - **Sensors**
  - Thermal camera, radar, acoustic sensors
* - **Platform**
  - Fixed: stationary sensors monitoring a defined track section
* - **Setting**
  - Controlled real-world environment, day and night
* - **How MuFASA was used**
  - Iterative parameter refinement within one fixed architecture
```

## How MuFASA was used

- **One graph, many experiments.** Temporal decay rates and detection thresholds were varied systematically to
  characterize the behaviour under day and night conditions: change a parameter, re-run, inspect the output.
- **From recorded to live.** Data was recorded and analysed offline first. The same graph then went live by
  exchanging the file input nodes for streaming input nodes, connected to the sensors via ROS2.

## The Fusion Graph

One of the sensor combinations of the trial: each sensor accumulates its detections into a probability map,
the three maps are fused, and a threshold turns the fused map into alarms.

```{code-cell}
from mufasa import BoundingBox, Graph
from mufasa.io.inputs import GeoJsonInput
from mufasa.io.outputs import Visualization
from mufasa.nodes import POM, BayesianFusion, Threshold

# Input nodes: one per sensor
thermal = GeoJsonInput("railway/thermal.geojson")
radar = GeoJsonInput("railway/radar.geojson")
acoustic = GeoJsonInput("railway/acoustic.geojson")

# Processing nodes: each sensor with its own decay and baseline confidence
fused = BayesianFusion()(
    POM(decay_s=3, prior=0.7)(thermal),
    POM(decay_s=5, prior=0.7)(radar),
    POM(decay_s=10, prior=0.55)(acoustic),
)
alarms = Threshold(threshold=0.88)(fused)

# Output node: keeps the sensor detections, the fused map and the alarms for plotting
vis = Visualization(snapshot_interval_s=1)(thermal, radar, acoustic, fused, alarms)

graph = Graph(
    inputs=[thermal, radar, acoustic],
    outputs=[vis],
    crs="EPSG:32633",
    bbox=BoundingBox(16.838758, 48.252595, 16.840809, 48.252971),
    resolution=(0.5, 0.5),
)
```

## Try it

We can't publish the trial data, so here is a synthetic replica of one of its scenarios: a group of two
committing graffiti. They walk along the tracks, chatting and rattling their spray cans, cross the tracks,
and split up: one sprays a parked wagon while the other keeps watch, until both flee. The site is a fictitious
one along an open line, with the layout of the trial. The detections are invented but behave like the trial's
sensors: the thermal cameras see the two people all the time, the radar only while they walk towards or away from
it, and the acoustic sensors only report the direction of speech, rattling and spraying. Download the files into
a folder `railway` to run the code above yourself:
{download}`thermal.geojson <railway/thermal.geojson>`,
{download}`radar.geojson <railway/radar.geojson>`,
{download}`acoustic.geojson <railway/acoustic.geojson>`.

```{code-cell}
graph.run()
```

A moment during the spraying: the lookout stands on the left, the sprayer at the wagon on the right.
The thermal cameras see both of them, the radar sees neither, as both stand still, and the acoustic sensor hears
spraying in the direction of the wagon. Only where the camera and the microphones agree, at the sprayer, does the
fused probability exceed the threshold and raise an alarm. Camera alone (the lookout) or microphones alone (the rest
of the sound's direction) stay below it.

```{code-cell}
:tags: [hide-input]

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

moment = dict(start=86, end=89, basemap="satellite")
fig, (sensors, result) = plt.subplots(2, 1, figsize=(12, 8))

# Inputs of vis by position: 0 thermal, 1 radar, 2 acoustic, 3 fused, 4 alarms
vis.show(2, ax=sensors, color="tab:blue", title="What the sensors report", **moment)
vis.show(0, ax=sensors, color="lime", **moment)
vis.show(1, ax=sensors, color="orange", **moment)
sensors.legend(handles=[
    Patch(color="lime", label="thermal camera: person"),
    Patch(color="orange", label="radar: movement"),
    Patch(color="tab:blue", label="acoustic: direction of a sound"),
], loc="upper left", fontsize=9)

vis.show(3, ax=result, title="What the Fusion Graph makes of it: fused probability", **moment)
vis.show(4, ax=result, color="red", **moment)
result.legend(handles=[Patch(color="red", label="alarm")], loc="upper left", fontsize=9)

for ax in (sensors, result):
    ax.set(xticks=[], yticks=[], xlabel="", ylabel="")  # Coordinates don't matter here
fig.tight_layout()
```

:::{tip}
Experiment with it: drop a sensor from `BayesianFusion`, or change a decay rate or the threshold,
and see how the alarm changes. That is exactly how the parameters were tuned in the trial.
:::

## References

**Project:** [MOBILIZE](https://projekte.ffg.at/projekt/5258433e-f36b-1410-85c1-00d3c07d99bb),
funded by the Austrian *Mobility of the Future* programme.

**Publications:**

- M. Hubner, K. Wohlleben, M. Litzenberger, S. Veigl, A. Opitz, S. Grebien, and M.-T. Dvorak,
  "A Bayesian approach – data fusion for robust detection of vandalism and trespassing related events in the
  context of railway security," *27th International Conference on Information Fusion (FUSION)*, 2024.
- M. Hubner, K. Wohlleben, M. Litzenberger, S. Veigl, A. Opitz, S. Grebien, F. Graf, A. Haderer, S. Rechbauer,
  and S. Poltschak, "Robust detection of critical events in the context of railway security based on multimodal
  sensor data fusion," *Sensors*, vol. 24, no. 13, 2024.
- M. Hubner, J. Nausner, and K. Wohlleben, "Advanced sensor fusion for railway security – a hierarchical
  graph-based approach," *Sensor Data Fusion: Trends, Solutions, Applications (SDF)*, 2024.
