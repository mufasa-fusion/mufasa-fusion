# Going Live

A Fusion Graph that is developed on recorded data runs on live data with the same fusion logic.
The recommended way to go live is to embed MuFASA in your messaging system. Install `mufasa-fusion`
in the application that talks to your MQTT broker, Kafka cluster or ROS 2 network, and run the graph there.
The graph then doesn't distinguish whether a message comes from a live sensor or from a replayed recording, such as a rosbag.

```{raw} html
<figure class="mf-golive">
<svg viewBox="0 0 760 290" role="img"
     aria-label="A messaging system contains live sensors and a replayed recording, both publishing to the same topics. Your application, with mufasa-fusion installed, runs the Fusion Graph: Input nodes subscribe, Processing nodes fuse, Output nodes publish to decision support.">
  <defs>
    <marker id="mf-gl-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path class="mf-gl-arrowhead" d="M0,0 L10,5 L0,10 z"/>
    </marker>
  </defs>

  <!-- Messaging system -->
  <rect class="mf-gl-system" x="4" y="14" width="752" height="270" rx="10"/>
  <text class="mf-gl-label mf-gl-label-system" x="20" y="14">Messaging system · MQTT, Kafka, ROS 2, …</text>

  <!-- Publishers -->
  <rect class="mf-gl-ext" x="20" y="62" width="135" height="60" rx="6"/>
  <text class="mf-gl-ext-text" x="87.5" y="87"><tspan class="mf-gl-title">Sensors</tspan><tspan x="87.5" dy="19">live</tspan></text>

  <rect class="mf-gl-ext mf-gl-rec" x="20" y="186" width="135" height="60" rx="6"/>
  <text class="mf-gl-ext-text mf-gl-rec" x="87.5" y="211"><tspan class="mf-gl-title">Recording</tspan><tspan x="87.5" dy="19">offline</tspan></text>

  <!-- Your application -->
  <rect class="mf-gl-app" x="190" y="44" width="425" height="222" rx="10"/>
  <text class="mf-gl-label mf-gl-label-app" x="204" y="44">Your application · pip install mufasa-fusion</text>

  <!-- Fusion Graph -->
  <rect class="mf-gl-graph" x="206" y="84" width="393" height="164" rx="10"/>
  <text class="mf-gl-label mf-gl-label-graph" x="220" y="84">Fusion Graph</text>

  <rect class="mf-gl-node mf-gl-io" x="222" y="128" width="95" height="66" rx="6"/>
  <text class="mf-gl-node-text mf-gl-io" x="269.5" y="155"><tspan class="mf-gl-title">Input nodes</tspan><tspan x="269.5" dy="19">subscribe</tspan></text>

  <rect class="mf-gl-node mf-gl-proc" x="352" y="128" width="101" height="66" rx="6"/>
  <text class="mf-gl-node-text mf-gl-proc" x="402.5" y="155"><tspan class="mf-gl-title">Processing</tspan><tspan x="402.5" dy="19">unchanged</tspan></text>

  <rect class="mf-gl-node mf-gl-io" x="488" y="128" width="95" height="66" rx="6"/>
  <text class="mf-gl-node-text mf-gl-io" x="535.5" y="155"><tspan class="mf-gl-title">Output nodes</tspan><tspan x="535.5" dy="19">publish</tspan></text>

  <!-- Subscribers -->
  <rect class="mf-gl-ext" x="644" y="128" width="100" height="66" rx="6"/>
  <text class="mf-gl-ext-text" x="694" y="155"><tspan class="mf-gl-title">Decision</tspan><tspan x="694" dy="19">support</tspan></text>

  <!-- Arrows: each ends exactly on the left edge of its target -->
  <path class="mf-gl-edge" d="M155,92 C190,92 190,150 222,150" marker-end="url(#mf-gl-arrow)"/>
  <path class="mf-gl-edge mf-gl-rec" d="M155,216 C190,216 190,172 222,172" marker-end="url(#mf-gl-arrow)"/>
  <path class="mf-gl-edge" d="M317,161 H352" marker-end="url(#mf-gl-arrow)"/>
  <path class="mf-gl-edge" d="M453,161 H488" marker-end="url(#mf-gl-arrow)"/>
  <path class="mf-gl-edge" d="M583,161 H644" marker-end="url(#mf-gl-arrow)"/>
</svg>
</figure>
```

## Why swapping the I/O is all it takes

Two design decisions make the transition from recorded to live data a matter of the Input and Output nodes:

- **The I/O boundary is the only interface to the outside world.**
  MuFASA works on the {doc}`detection level <../design-principles>`. Input and Output nodes translate
  external data into {class}`~mufasa.location.Location`s and {class}`~mufasa.map.Map`s and back.
- **Processing is event-driven.**
  Every node updates its state as soon as it receives an observation. There's no separate clock driving the graph,
  so the same graph runs against a recording during prototyping and against a live stream in operation.

:::{note}
Swapping the I/O nodes is all it takes *at the implementation level*. A live deployment still differs from an offline one. Recorded data is clean and ordered by construction, live data isn't. MuFASA doesn't close that gap by architecture alone, but it helps you work through it. The same quick iteration and inspection that help with prototyping help you understand what a live deployment surfaces, and act on it quickly.
:::

The guides below follow two of our {doc}`showcases <../../showcases/index>`.
The **ROS 2** guide follows *Railway Security*, where the recorded data was analyzed offline first
and the same graph then went live on ROS 2. The **MQTT** guide follows *Land & Maritime Border Security*.


## Publish-subscribe architecture

Embedding MuFASA in a messaging system follows a simple pattern. The graph runs inside a client or node of that system. Each time a subscriber callback receives a message, it translates the message into MuFASA's minimal representation and passes it to a streaming Input node. Only this translation step is specific to the messaging system and must be known and implemented by the user. The Fusion Graph itself is never touched. Because node parameters are explicit, they can be exposed through the messaging system's own configuration, for example as ROS 2 node parameters.

MuFASA is primarily used in, but not limited to, publisher-subscriber architectures in live systems. Sensors publish their detections on topics. A Fusion Graph subscribes to those topics with its Input nodes and publishes its results with its Output nodes. Decision support, such as an alarm dashboard, subscribes to the results.

The following guides show the transition for two messaging systems:

```{toctree}
:maxdepth: 1

mqtt
ros2
```
