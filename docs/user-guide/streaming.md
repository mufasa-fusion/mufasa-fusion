---
file_format: mystnb
---

```{code-cell}
:tags: [remove-cell]
import os.path
os.chdir(os.path.join("..", "_data"))
```

# Custom Data Sources

This guide shows how to connect Fusion Graphs to not (yet) built-in data sources.
It focuses on integrating external systems that stream live data and implementing new input nodes.
Moreover, it covers extending MuFASA for recorded data and demonstrates common usage patterns around inputs.

:::{admonition} You don't need a new node!
:class: hint
Implementing a new node might just be overkill in some situations.
The same goals might be achieved by some boilerplate preparation code.
In the spirit of rapid prototyping, these boxes highlight how to use your custom data with existing core inputs.

Implementing a dedicated node has some advantages, too:

- It gives you a coherent unit of code that you can share with others, for example by contributing it back to MuFASA.
- It allows you to serialize and re-import your Fusion Graph (see {ref}`dict-config`).
- It makes your extensions explicit in the Fusion Graph and visible at a glance.
:::

## Simulating a Live Sensor

Throughout this guide, we simulate a live sensor by a TCP server that sends detections
as GeoJSON Features over each connection, one per line with a random few seconds delay in between.
The demo server and client code is largely based on Python's official `socketserver` examples[^socketserver_examples].

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Sensor simulation TCP server
    code_prompt_hide: Sensor simulation TCP server
---
# FeatureSendingRequestHandler

import json
import socketserver
import time

SEP = b"\r\n"

with open("sensor_b.geojson") as features_file:
    features = json.load(features_file)["features"]

features_bin = [json.dumps(f).encode() + SEP for f in features]

class FeatureSendingRequestHandler(socketserver.BaseRequestHandler):
    """Simulates a sensor that is sending GeoJSON Feature lines"""

    def handle(self):
        for feature in features_bin:
            self.request.sendall(feature)
            time.sleep(.1 + .1 * random.random())


# server_thread

import contextlib
import threading

ADDRESS = "localhost", 8000

# Allow reusing the same port immediately after server shutdown (for repeated calls)
socketserver.ThreadingTCPServer.allow_reuse_address = True

@contextlib.contextmanager
def on_bg_thread(target, *args, **kwargs):
    t = threading.Thread(target=target, args=args, kwargs=kwargs)
    t.start()
    try:
        yield
    finally:
        t.join()

@contextlib.contextmanager
def server_thread(address: tuple[str, int], handler: socketserver.BaseRequestHandler):
    """Starts a sensor server on a separate thread on enter and shuts it down on exit"""
    with (
        socketserver.ThreadingTCPServer(address, handler) as server,
        on_bg_thread(server.serve_forever),
    ):
        try:
            yield
        finally:
            server.shutdown()
```

:::{note}
For this tutorial, we use a context manager for starting and stopping the server
that you wrap your fusion code with like so:

```python
with server_thread(ADDRESS, FeatureSendingRequestHandler):  # Demo only!
    graph.run()
```

In a real-world scenario, you don't need something equivalent! You certainly have an externally managed sensor.
Within the fusion code, you'd take it for granted that the system is up and running.
:::

(common-basics)=
## Integration Basics

To use that demo sensor in fusion systems, we extend MUFASA with a custom {class}`~mufasa.io.inputs.base.InputNode` subclass.
They are responsible for connecting to the data streams of external systems and for converting them to
MuFASA's own data models. And since it is a live sensor -- and we want continuous updates to our outputs[^no_stream_out]
-- we implement a streaming one derived from {class}`~mufasa.io.inputs.streaming.StreamingInputNode`.

Here's a quick checklist that applies to every input node:

:::{list-table}
:header-rows: 1
- * &#9745;
  * Ref
  * Requirement
  * Notes
- * &#9745;
  * #1
  * Derives from {class}`~mufasa.io.inputs.base.InputNode`.
  * Extending {class}`~mufasa.io.inputs.streaming.StreamingInputNode` signals to the {class}`~mufasa.graph.Graph`
    that the node will do blocking calls to wait for new messages.
- * &#9745;
  * #2
  * Specifies its {attr}`~mufasa.node.Node._output_type`.
  * In this example, we equivalently could have subclassed {class}`~mufasa.io.inputs.streaming.ObservationStreamingInput`
    to inherit producing {class}`~mufasa.location.Observation`.
- * &#9745;
  * #3
  * Converts to its output type.
  * We provide a helper function in this example that we will use later in concrete subclasses.
- * &#9744;
  * #4a
  * Yields its data from {class}`~mufasa.io.inputs.base.InputNode.items()`.
  * This will depend on the type of input node and be implemented in subclasses in the following sections.
- * &#9744;
  * #4b
  * Or {func}`~mufasa.io.inputs.streaming.StreamingInputNode.ingest`s data items.
  * For {class}`~mufasa.io.inputs.streaming.StreamingInputNode`s only!
- * &#9745;
  * #5a
  * Exports it's parameters in {func}`~mufasa.node.Node.get_config()`.
  * 
- * &#9744;
  * #5b
  * Registers with the {attr}`~mufasa.registry.NODE_REGISTRY` for imports.
  * Needs to be done for each concrete subclass separately.
:::

Checked items are covered by `GeoJsonObservationStreamingInput` implemented below
that serves as a base in the following concrete sections.
The `#N` references annotate respective lines in code samples and their explanations.

(basic-node)=
```{code-cell}
from mufasa.location import Observation
from mufasa.io.inputs import StreamingInputNode
from shapely.geometry.geo import shape

_start_time = time.monotonic()

class GeoJsonObservationStreamingInput(StreamingInputNode):  #1
    _output_type = Observation  #2

    def __init__(
            self,
            address: tuple[str, int],
            ts_col: str = "timestamp",
            conf_col: str = "confidence",
            props_default: dict[str, "Any"] | None = None,
    ):
        super().__init__()
        self.address = address
        self.ts_col = ts_col
        self.conf_col = conf_col
        self.props_default = props_default if props_default is not None else {}

    def feature_to_observation(self, raw: str | bytes) -> Observation:  #3
        """Converts a GeoJSON Feature to a MuFASA Observation"""
        feature = json.loads(raw)
        geom = shape(feature["geometry"])
        props = self.props_default | feature.get("properties", {})
        # Utilize upscaled arrival timestamp for demo purposes!
        ts = props.pop(self.ts_col, 10 * (time.monotonic() - _start_time))
        conf = props.pop(self.conf_col, Observation.confidence)
        return Observation(geom, ts, props, conf)

    def get_config(self) -> dict:  #5a
        return {
            "address": self.address,
            "ts_col": self.ts_col,
            "conf_col": self.conf_col,
            "props_default": self.props_default
        }
```

(pull-client)=
## For Pull Clients

Pull clients provide either a function that blocks to wait for a single message
or a generator function that does so repeatedly, yielding the messages.
We go for a generator function in this example. You can easily replace it with a receiver function called in a loop.

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Sensor simulation TCP pull client
    code_prompt_hide: Sensor simulation TCP pull client
---
import random
import socket

def sock_recv_lines(address: tuple[str, int]):
    """Yields lines of text received from a socket connected to the given address"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect(address)
        yield from sock.makefile()
```

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Pull client usage outside MuFASA
    code_prompt_hide: Pull client usage outside MuFASA
---
with server_thread(ADDRESS, FeatureSendingRequestHandler):
    for line in sock_recv_lines(ADDRESS):
            print(f"[client] received data:", line)
```

To integrate it, we overwrite {func}`~mufasa.io.inputs.streaming.StreamingInputNode.items()`[{sup}`#4a`](#pull-node)
so that it yields the messages from the generator after conversion[{sup}`#3`](#pull-node).
We derive the node from the one developed in {ref}`common-basics`[{sup}`#1`](#pull-node) to inherit
output type, conversion and config logic and also register the node for later imports[{sup}`#5b`](#pull-node).

(pull-node)=
```{code-cell}
from mufasa.registry import NODE_REGISTRY

class GeoJsonObservationPullInput(GeoJsonObservationStreamingInput):  #1
    def items(self):  #4a
        for line in sock_recv_lines(self.address):
            yield self.feature_to_observation(line)  #3

NODE_REGISTRY[GeoJsonObservationPullInput.__name__] = GeoJsonObservationPullInput  #5b
```

Usage:

```{code-cell}
from mufasa import Graph
from mufasa.io.outputs import LocationOutput

pull_a = GeoJsonObservationPullInput(ADDRESS, props_default={"track": "A"})
pull_b = GeoJsonObservationPullInput(ADDRESS, props_default={"track": "B"})
pull_out = LocationOutput()(pull_a, pull_b)
pull_graph = Graph([pull_a, pull_b], [pull_out])

pull_graph.plot_graph()
```

```{code-cell}
with server_thread(ADDRESS, FeatureSendingRequestHandler):  # Demo only!
    pull_graph.run()

pull_out.result
```

## For Recorded Sources

Implementing a dedicated input node for recorded data is similar to one {ref}`pull-client` with these two exceptions:

- Subclass an {class}`~mufasa.io.inputs.base.InputNode` (that is not a {class}`~mufasa.io.inputs.streaming.StreamingInputNode`, too).
- Overwrite {func}`~mufasa.io.inputs.streaming.StreamingInputNode.items()` to return a collection of (or yield) your data at once.

:::{admonition} You don't need a new node!
:class: hint
Just read and convert the data beforehand and pass it in via a
{class}`~mufasa.io.inputs.python_object.LocationInput` or {class}`~mufasa.io.inputs.python_object.MapInput` node.
:::

(push-client)=
## For Push Clients

Push clients have their own blocking event loops that push each message received to a user-supplied callback function.

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Sensor simulation TCP push client
    code_prompt_hide: Sensor simulation TCP push client
---
def sock_recv_loop(address: tuple[str, int], callback, end_msg):
    """Pulls lines of text from a socket connected to address and pushes them to callback"""
    for line in sock_recv_lines(address):
        callback(line)
    callback(end_msg)
```

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Push client usage outside MuFASA
    code_prompt_hide: Push client usage outside MuFASA
---
def cb(msg):
    if msg == "END":
        print("-- END --")
    else:
        print(f"[client] received data:", line)

with server_thread(ADDRESS, FeatureSendingRequestHandler):
    sock_recv_loop(ADDRESS, cb, "END")
```

To integrate them, we overwrite {func}`~mufasa.io.inputs.streaming.StreamingInputNode.items()`[{sup}`#4a`](#push-usage)
to run the loop on a background thread[{sup}`#A`](#push-usage).
Yield from its superclass implementation[{sup}`#B`](#push-usage) to forward ingested data!
The callback function uses {func}`~mufasa.io.inputs.streaming.StreamingInputNode.ingest`[{sup}`#4b`](#push-node)
to pass the converted data on (Internally, there's a queue connecting those two). This example uses a dedicated end message to
{func}`~mufasa.io.inputs.streaming.StreamingInputNode.stop`[{sup}`#C`](#push-node) what indicates the data stream's end.
You have to have some end condition or else `graph.run()` will go forever -- even though sensor data streams are typically endless.
Finally, we derive this node from the one developed in {ref}`common-basics`[{sup}`#1`](#push-node) to inherit
output type, conversion and config logic and also register the node for imports[{sup}`#5b`](#push-node).

(push-node)=
```{code-cell}
class GeoJsonObservationPushInput(GeoJsonObservationStreamingInput):  #1
    END_MSG = "END"

    def items(self):  #4a
        with on_bg_thread(sock_recv_loop, self.address, self.ingest_message, self.END_MSG):  #A
            yield from super().items() #B

    def ingest_message(self, msg: str) -> None:
        if msg == self.END_MSG:  #C
            self.stop()
        else:
            self.ingest(self.feature_to_observation(msg))  #3 #4b

NODE_REGISTRY[GeoJsonObservationPushInput.__name__] = GeoJsonObservationPushInput  #5b
```

Usage:

```{code-cell}
push_a = GeoJsonObservationPushInput(ADDRESS, props_default={"track": "A"})
push_b = GeoJsonObservationPushInput(ADDRESS, props_default={"track": "B"})
push_out = LocationOutput()(push_a, push_b)
push_graph = Graph([push_a, push_b], [push_out])

push_graph.plot_graph()
```

(push-usage)=
```{code-cell}
with server_thread(ADDRESS, FeatureSendingRequestHandler):  # Demo only!
    push_graph.run()

push_out.result
```

:::{admonition} You don't need a new node!
:class: hint
Use a plain {class}`~mufasa.io.inputs.streaming.ObservationStreamingInput` node (or similar as appropriate to your use case).
Write a new callback function that you pass to your client library. Integrate your conversion logic there
and make it call {func}`~mufasa.io.inputs.streaming.StreamingInputNode.ingest` of your plain node instance.
:::

(push-alt)=
```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Alternative core node + boilerplate code
    code_prompt_hide: Alternative core node + boilerplate code
---
from mufasa.io.inputs import ObservationStreamingInput
from functools import partial

alt_a = ObservationStreamingInput()
alt_b = ObservationStreamingInput()
alt_out = LocationOutput()(alt_a, alt_b)
alt_graph = Graph([alt_a, alt_b], [alt_out])

def push_cb(node: ObservationStreamingInput, props_default: dict, msg: str):
    if msg == "END":
        node.stop()
    else:
        # Conversion logic and inges() inside callback
        feature = json.loads(msg)
        geom = shape(feature["geometry"])
        props = props_default | feature.get("properties", {})
        # Utilize upscaled arrival timestamp for demo purposes!
        ts = props.pop("timestamp", 10 * (time.monotonic() - _start_time))
        conf = props.pop("confidence", Observation.confidence)
        node.ingest(Observation(geom, ts, props, conf))

with (
    server_thread(ADDRESS, FeatureSendingRequestHandler),  # Demo only!
    # Start reception loops outside MuFASA and pass callbacks that ingest()
    on_bg_thread(sock_recv_loop, ADDRESS, partial(push_cb, alt_a, {"track": "A"}), "END"),
    on_bg_thread(sock_recv_loop, ADDRESS, partial(push_cb, alt_b, {"track": "B"}), "END"),
):
    alt_graph.run()

alt_out.result
```

## Example: MQTT

Next, we replace the TCP transport with MQTT[^MQTT] for a more realistic scenario.
We will use the Paho[^paho_mqtt] MQTT client library, so install it with:

```bash
pip install paho-mqtt
```

And we need a MQTT broker running in the background, for example:

```bash
docker run -p 1883:1883 eclipse-mosquitto
```

We will still use a simple script to simulate a sensor publishing detections, again as GeoJSON Feature lines.

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Publisher simulating a sensor
    code_prompt_hide: Publisher simulating a sensor
---
from paho.mqtt import client as mqtt

HOST = "localhost"
PORT = 1883
TOPIC = "mufasa/sensor/a"

def mqtt_pub(host: str, port: int, topic: str, end_msg: bytes):
    """Publishes GeoJSON Features over MQTT"""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.loop_start()
    try:
        client.connect(host, port)
        time.sleep(2)
        try:
            for feature in features_bin:
                client.publish(TOPIC, feature)
                time.sleep(.1 + .1 * random.random())
            client.publish(topic, end_msg)
        finally:
            client.disconnect()
    finally:
        client.loop_stop()
```

Since Paho offers a push client, the input node is similar to the one defined in {ref}`push-client`.
The most notable difference is that we need to disconnect the client after receiving the end
message[{sup}`#D`](#mqtt-node) or else it will stay subscribed to the topic forever.

(mqtt-node)=
```{code-cell}
from paho.mqtt import subscribe

class GeoJsonObservationPahoInput(GeoJsonObservationStreamingInput):  #1
    END_MSG = b"END"

    def __init__(self, address: tuple[str, int], topic: str, **kwargs):
        super().__init__(address, **kwargs)
        self.topic = topic

    def get_config(self):  #5a
        return {"topic": self.topic, **super().get_config()}

    def items(self):  #4a
        with on_bg_thread(subscribe.callback, self.paho_ingest_message, self.topic, 0, None, *self.address):  #A
            yield from super().items()  #B

    def paho_ingest_message(self, client: mqtt.Client, userdata, message: bytes) -> None:
        msg = message.payload
        if msg == self.END_MSG:  #C
            self.stop()
            # Disconnect the client so that the subscriber thread finishes
            client.disconnect()  #D
        else:
            self.ingest(self.feature_to_observation(msg))  #3 #4b

NODE_REGISTRY[GeoJsonObservationPahoInput.__name__] = GeoJsonObservationPahoInput  #5b
```

Usage:

```{code-cell}
mqtt_a = GeoJsonObservationPahoInput((HOST, PORT), TOPIC, props_default={"track": "A"})
mqtt_b = GeoJsonObservationPahoInput((HOST, PORT), TOPIC, props_default={"track": "B"})
mqtt_out = LocationOutput()(mqtt_a, mqtt_b)
mqtt_graph = Graph([mqtt_a, mqtt_b], [mqtt_out])

mqtt_graph.plot_graph()
```

```{code-cell}
with on_bg_thread(mqtt_pub, HOST, PORT, TOPIC, GeoJsonObservationPushInput.END_MSG):  # Demo only!
    mqtt_graph.run()

mqtt_out.result
```

## Example: ROS 2

Robots and autonomous systems commonly exchange sensor data via ROS 2[^ros2] topics.
Its Python client library rclpy[^rclpy] is a push client, too, but it differs from Paho in one important aspect:
the ROS *executor* owns the event loop (`rclpy.spin()`) and calls your subscription callbacks.
And in ROS, everything is a node that is started with `ros2 run`, configured with parameters and wired up in launch files.

So instead of hiding the client inside a MuFASA input node, we turn things around:
a ROS node hosts the Fusion Graph. This is the {ref}`alternative to a dedicated input node <push-alt>` from above,
applied to both ends of the graph:

- Subscription callbacks convert messages and {func}`~mufasa.io.inputs.streaming.StreamingInputNode.ingest`
  them into plain {class}`~mufasa.io.inputs.streaming.ObservationStreamingInput` nodes, one per topic.
- A {class}`~mufasa.io.outputs.streaming.StreamingOutputNode` publishes each result to an output topic.

:::{note}
The examples in this section are not executed when building this documentation, because rclpy can't be installed with pip.
Run them in a ROS 2 environment as described in {ref}`ros-run`.
:::

To keep the focus on the integration, messages are GeoJSON Features again, sent as `std_msgs/String`.
Real-world systems use typed messages instead, for example `sensor_msgs/NavSatFix` for positions,
or custom ones for detections. Their conversion goes in the same places.

The simulated sensor is a minimal ROS node publishing the features to every topic given on the command line:

```python
# sensor_sim.py

import json
import random
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

END_MSG = "END"


def main():
    """Publishes GeoJSON Features to each topic given on the command line"""
    rclpy.init()
    node = Node("sensor_sim")
    publishers = [node.create_publisher(String, topic, 10) for topic in sys.argv[1:]]

    with open("sensor_b.geojson") as features_file:
        features = json.load(features_file)["features"]

    # Wait for the fusion node to subscribe, or else the first messages get lost
    while any(pub.get_subscription_count() == 0 for pub in publishers):
        time.sleep(.1)

    for feature in features:
        for pub in publishers:
            pub.publish(String(data=json.dumps(feature)))
        time.sleep(.1 + .1 * random.random())
    for pub in publishers:
        pub.publish(String(data=END_MSG))

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
```

The fusion node creates its publisher first[{sup}`#A`](#ros-node), so it exists before the graph can produce any results.
Then it builds the graph with one input per topic and subscribes to the topics.
Since `rclpy.spin()` blocks the main thread, the graph runs on a background thread[{sup}`#B`](#ros-node).
The subscription callback converts messages[{sup}`#3`](#ros-node) and ingests them[{sup}`#4b`](#ros-node).
It catches conversion errors, so a single malformed message doesn't take down the whole node[{sup}`#C`](#ros-node).
The output node's callback converts results back to GeoJSON and publishes them[{sup}`#D`](#ros-node).
Finally, destroying the ROS node stops the graph and waits for its thread[{sup}`#E`](#ros-node).

:::{note}
The graph's `crs` parameter sets the coordinate reference system that MuFASA computes in.
The node uses a UTM zone by default, so distances are in metres.
Input nodes project incoming WGS84 geometries into it, but output nodes don't project results back.
That's why `publish_location()` transforms them to WGS84 before converting them to GeoJSON.
:::

(ros-node)=
```python
# fusion_node.py

import json
import threading
from functools import partial

from pyproj import Transformer
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from shapely.geometry import mapping, shape
from shapely.ops import transform
from std_msgs.msg import String

from mufasa import Graph
from mufasa.io.inputs import ObservationStreamingInput
from mufasa.io.outputs import StreamingOutputNode
from mufasa.location import Location, Observation

END_MSG = "END"


class FusionNode(Node):
    """ROS 2 node hosting a Fusion Graph with one streaming input per topic"""

    def __init__(self):
        super().__init__("mufasa_fusion")
        input_topics = self.declare_parameter(
            "input_topics", ["/mufasa/sensor/a", "/mufasa/sensor/b"]).value
        output_topic = self.declare_parameter("output_topic", "/mufasa/fused").value
        crs = self.declare_parameter("crs", "EPSG:32633").value  # UTM zone of the demo data

        self.publisher = self.create_publisher(String, output_topic, 10)  #A

        self.inputs = {topic: ObservationStreamingInput() for topic in input_topics}
        out = StreamingOutputNode(self.publish_location)(*self.inputs.values())
        self.graph = Graph(list(self.inputs.values()), [out], crs=crs)
        # The graph projects WGS84 inputs to its CRS, but GeoJSON outputs need WGS84 again
        self.to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform

        for topic, node in self.inputs.items():
            self.create_subscription(String, topic, partial(self.on_message, node, topic), 10)

        self.graph_thread = threading.Thread(target=self.run_graph)  #B
        self.graph_thread.start()

    def on_message(self, node: ObservationStreamingInput, topic: str, msg: String) -> None:
        if msg.data == END_MSG:
            node.stop()
            return
        try:  #C
            feature = json.loads(msg.data)  #3
            props = {"topic": topic} | feature.get("properties", {})
            # std_msgs/String has no header, so use the arrival time
            ts = props.pop("timestamp", self.get_clock().now().nanoseconds / 1e9)
            conf = props.pop("confidence", Observation.confidence)
            node.ingest(Observation(shape(feature["geometry"]), ts, props, conf))  #4b
        except Exception as e:
            self.get_logger().error(f"Dropping message on {topic}: {e}")

    def publish_location(self, location: Location) -> None:  #D
        props = {"timestamp": location.timestamp, **location.properties}
        if isinstance(location, Observation):
            props["confidence"] = location.confidence
        geometry = mapping(transform(self.to_wgs84, location.geometry))
        feature = {"type": "Feature", "geometry": geometry, "properties": props}
        self.publisher.publish(String(data=json.dumps(feature)))

    def run_graph(self) -> None:
        self.graph.run()
        rclpy.try_shutdown()  # Demo only! Stop spinning once all inputs have ended

    def destroy_node(self):  #E
        self.graph.stop()
        self.graph_thread.join()
        return super().destroy_node()


def main():
    rclpy.init()
    node = None
    try:
        node = FusionNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
```

In this demo, the node shuts itself down once all inputs have received their end message.
A real fusion node runs until it is stopped with {kbd}`Ctrl+C` or by its launch system.
Either way, `destroy_node()` stops the graph.

:::{admonition} Quality of Service
:class: tip
Publishers and subscribers only connect if their QoS[^ros2_qos] settings are compatible.
The examples use ROS's default (reliable delivery, a history depth of 10).
Many sensor drivers publish with *best effort* reliability, though.
Subscribing to them requires a matching profile, for example
`QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)` from `rclpy.qos`.
:::

(ros-run)=
### Running the Example

The simplest way to get a ROS 2 environment is the official Docker image.
Save the two scripts above to a folder together with `sensor_b.geojson` from this documentation's data,
and start a container from the root of the MuFASA repository with that folder mounted:

```bash
docker run -it --rm --name ros-mufasa \
    -v "$PWD":/mufasa:ro -v /path/to/scripts:/work -w /work \
    ros:humble bash
```

Inside the container, install MuFASA and start the fusion node:

```bash
apt-get update && apt-get install -y python3-pip
# Ubuntu 22.04's pip is too old for MuFASA's pyproject.toml
pip install --upgrade pip
cp -r /mufasa /tmp/mufasa && pip install /tmp/mufasa
source /opt/ros/humble/setup.bash
python3 fusion_node.py
```

In a second terminal, watch the fused results:

```bash
docker exec -it ros-mufasa bash
source /opt/ros/humble/setup.bash
ros2 topic echo --full-length /mufasa/fused std_msgs/msg/String
```

And in a third terminal, start the simulated sensor:

```bash
docker exec -it ros-mufasa bash
source /opt/ros/humble/setup.bash
python3 sensor_sim.py /mufasa/sensor/a /mufasa/sensor/b
```

The second terminal then shows each feature twice, once per input topic, for example:

```text
data: '{"type": "Feature", "geometry": {"type": "Point", "coordinates": [16.426643559839174, 48.26840868576795]}, "properties": {"timestamp": 1793183493.4454303, "topic": "/mufasa/sensor/a", "confidence": 0.9433776719597745}}'
---
data: '{"type": "Feature", "geometry": {"type": "Point", "coordinates": [16.426643559839174, 48.26840868576795]}, "properties": {"timestamp": 1793183493.4456568, "topic": "/mufasa/sensor/b", "confidence": 0.9433776719597745}}'
---
```

To reach nodes on other machines, the usual ROS networking applies:
all participants need the same `ROS_DOMAIN_ID`, and in Docker you need to use `--network host`.

[^socketserver_examples]: Python Standard Library, `socketserver` module's examples,
<https://docs.python.org/3/library/socketserver.html#examples>
[^no_stream_out]: Assuming we would use streaming-capable output nodes, too -- What we don't do in this demo.
[^MQTT]: MQTT, <https://mqtt.org/>
[^paho_mqtt]: Eclipse Paho MQTT Python Client, <https://eclipse.dev/paho/files/paho.mqtt.python/html/index.html>
[^ros2]: ROS 2 Documentation, <https://docs.ros.org/en/humble/>
[^rclpy]: rclpy, ROS 2's Python client library, <https://docs.ros.org/en/humble/p/rclpy/>
[^ros2_qos]: ROS 2 Quality of Service settings, <https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html>
