# Showcases

MuFASA has been applied across domains that differ in what is detected, where the sensors sit and which
modalities they use. Two of them were tested in controlled real-world trials.

::::{container} mf-showcase-cards

:::{container}
**Border security**

<span class="mf-status mf-status-tested">Field-tested</span>

Detect and track vessels, vehicles and people moving between water and land.

<span class="mf-chips">Moving objects · Fixed and mobile sensors · SWIR, RGB, thermal</span>

*Page in preparation*
:::

:::{container}
**{doc}`Railway security <railway-security>`**

<span class="mf-status mf-status-tested">Field-tested</span>

Detect trespassing, sabotage and vandalism along railway corridors, by day and at night.

<span class="mf-chips">Moving and placed objects · Fixed sensors · Thermal, radar, acoustic</span>
:::

:::{container}
**CBRNE threats**

<span class="mf-status mf-status-simulation">In simulation</span>

Localize and classify static threats such as landmines and improvised explosive devices.

<span class="mf-chips">Static objects · Mobile sensors</span>

*Page in preparation*
:::

::::

## Compare them

| | Border security | Railway security | CBRNE threats |
|---|---|---|---|
| **Objects of interest** | Vessels, vehicles, persons | Persons, placed objects, vandalism | Static threats (buried) |
| **Objects move?** | Yes | Partly | No |
| **Platform** | Fixed and mobile (UAV) | Fixed | Mobile |
| **Sensors** | SWIR, RGB, thermal cameras | Thermal, radar, acoustic | Simulated |
| **How MuFASA was used** | Comparing fusion architectures | Tuning parameters of one architecture | Fusing evidence about static objects |
| **Status** | Field-tested | Field-tested | In simulation |

## Which one is closest to your problem?

- Your objects **move** and you combine **fixed and mobile** sensors: **border security**.
- **Fixed** sensors watch a **defined area**, and you need to tune them to changing conditions:
  {doc}`railway security <railway-security>`.
- Your objects are **static** and your sensors move: **CBRNE threats**.

:::{admonition} Have your own data?
:class: tip

MuFASA works on detections: all it needs is a position for each one, plus a timestamp and a confidence where
available. GeoJSON files go into a {class}`~mufasa.io.inputs.geojson.GeoJsonInput`, GeoTIFF rasters into a
{class}`~mufasa.io.inputs.geotiff.GeoTiffInput`, and Python objects into a
{class}`~mufasa.io.inputs.python_object.LocationInput`. The {doc}`../user-guide/tutorials` show the first steps.
:::

```{toctree}
:hidden:

railway-security
```
