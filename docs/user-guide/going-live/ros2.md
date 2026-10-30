# ROS 2

Robots and autonomous systems commonly exchange sensor data via ROS 2[^ros2] topics.
Its Python client library rclpy[^rclpy] is a push client, too, but it differs from Paho in one important aspect:
the ROS *executor* owns the event loop (`rclpy.spin()`) and calls your subscription callbacks.
And in ROS, everything is a node that is started with `ros2 run`, configured with parameters and wired up in launch files.

So instead of hiding the client inside a MuFASA input node, we turn things around:
a ROS node hosts the Fusion Graph. This is the {ref}`alternative to a dedicated input node <push-alt>`,
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

The script is split into parts, each marked by a heading:

- **Fusion Graph**: the actual MuFASA integration. `build_graph()` creates one streaming input per topic
  and a {class}`~mufasa.io.outputs.streaming.StreamingOutputNode` that hands each result to a callback.
  This is where you would add your fusion nodes.
- **Message conversion**: translates between ROS messages and MuFASA's data models.
- **ROS node**: the wrapper around the graph. Subscription callbacks ingest converted messages
  and the output callback publishes the results.
  Since `rclpy.spin()` blocks the main thread, the graph runs on a thread of its own.

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

END_MSG = "END"  # Demo only! Marks the end of a simulated sensor's data


# --- Fusion Graph -------------------------------------------------------------
# The actual MuFASA integration. Everything below connects it to ROS.

def build_graph(topics: list[str], crs: str, on_output):
    """Builds a Fusion Graph with one streaming input per topic, passing results to on_output"""
    inputs = {topic: ObservationStreamingInput() for topic in topics}
    # Add fusion nodes between the inputs and the output here
    out = StreamingOutputNode(on_output)(*inputs.values())
    graph = Graph(list(inputs.values()), [out], crs=crs)
    return graph, inputs


# --- Message conversion -------------------------------------------------------

def message_to_observation(msg: String, topic: str, arrival_time: float) -> Observation:
    """Converts a GeoJSON Feature message to a MuFASA Observation"""
    feature = json.loads(msg.data)
    props = {"topic": topic} | feature.get("properties", {})
    # std_msgs/String has no header with a timestamp, so fall back to the arrival time
    ts = props.pop("timestamp", arrival_time)
    conf = props.pop("confidence", Observation.confidence)
    return Observation(shape(feature["geometry"]), ts, props, conf)


def location_to_message(location: Location, to_wgs84) -> String:
    """Converts a MuFASA result to a GeoJSON Feature message in WGS84"""
    props = {"timestamp": location.timestamp, **location.properties}
    if isinstance(location, Observation):
        props["confidence"] = location.confidence
    # The graph computes in its own CRS and doesn't project results back
    geometry = mapping(transform(to_wgs84, location.geometry))
    return String(data=json.dumps({"type": "Feature", "geometry": geometry, "properties": props}))


# --- ROS node -----------------------------------------------------------------

class FusionNode(Node):
    """ROS 2 node that feeds topics into a Fusion Graph and publishes its results"""

    def __init__(self):
        super().__init__("mufasa_fusion")

        # Parameters, can be overridden with `--ros-args -p <name>:=<value>`
        input_topics = self.declare_parameter(
            "input_topics", ["/mufasa/sensor/a", "/mufasa/sensor/b"]).value
        output_topic = self.declare_parameter("output_topic", "/mufasa/fused").value
        crs = self.declare_parameter("crs", "EPSG:32633").value  # UTM zone of the demo data

        # Output: create the publisher before the graph can produce any results
        self.publisher = self.create_publisher(String, output_topic, 10)
        self.to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform

        # Fusion: the graph calls publish_result() with each result
        self.graph, self.inputs = build_graph(input_topics, crs, self.publish_result)

        # Inputs: one subscription per topic, each feeding its own graph input
        for topic, graph_input in self.inputs.items():
            self.create_subscription(String, topic, partial(self.on_message, graph_input, topic), 10)

        # rclpy.spin() blocks the main thread, so the graph runs on its own thread
        self.graph_thread = threading.Thread(target=self.run_graph)
        self.graph_thread.start()

    def on_message(self, graph_input: ObservationStreamingInput, topic: str, msg: String) -> None:
        """Subscription callback: passes each message on to the graph"""
        if msg.data == END_MSG:
            graph_input.stop()
            return
        try:
            arrival_time = self.get_clock().now().nanoseconds / 1e9
            graph_input.ingest(message_to_observation(msg, topic, arrival_time))
        except Exception as e:
            # Drop malformed messages instead of crashing the node
            self.get_logger().error(f"Dropping message on {topic}: {e}")

    def publish_result(self, location: Location) -> None:
        """Output callback: publishes each fusion result"""
        self.publisher.publish(location_to_message(location, self.to_wgs84))

    def run_graph(self) -> None:
        self.graph.run()  # Returns once all inputs have stopped
        rclpy.try_shutdown()  # Demo only! Stop spinning once all inputs have ended

    def destroy_node(self):
        """Stops the graph and waits for its thread before ROS tears down the node"""
        self.graph.stop()
        self.graph_thread.join()
        return super().destroy_node()


# --- Entry point --------------------------------------------------------------

def main():
    rclpy.init()
    node = None
    try:
        node = FusionNode()
        rclpy.spin(node)  # Runs the subscription callbacks until shutdown
    except (KeyboardInterrupt, ExternalShutdownException):
        pass  # Stopped with Ctrl+C, or by run_graph()
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
```

:::{note}
The graph's `crs` parameter sets the coordinate reference system that MuFASA computes in.
The node uses a UTM zone by default, so distances are in metres.
Input nodes project incoming WGS84 geometries into it, but output nodes don't project results back.
That's why `location_to_message()` transforms them back to WGS84.
:::

In this demo, the node shuts itself down once all inputs have received their end message.
A real fusion node runs until it is stopped with {kbd}`Ctrl+C` or by its launch system.
Either way, `destroy_node()` stops the graph.

(ros-run)=
## Running the Example

To feed the fusion node with data, a minimal ROS node simulates a sensor.
It publishes the features to every topic given on the command line.

::::{admonition} Sensor simulation ROS node
:collapsible: closed
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
::::

The simplest way to get a ROS 2 environment is the official Docker image.
Save `fusion_node.py` and `sensor_sim.py` to a folder together with [`sensor_b.geojson`](/_data/sensor_b.geojson),
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
If no messages arrive from a real sensor, check that its QoS[^ros2_qos] settings match the subscription's.
Many sensor drivers publish with *best effort* reliability, while the example subscribes with ROS's *reliable* default.

[^ros2]: ROS 2 Documentation, <https://docs.ros.org/en/humble/>
[^rclpy]: rclpy, ROS 2's Python client library, <https://docs.ros.org/en/humble/p/rclpy/>
[^ros2_qos]: ROS 2 Quality of Service settings, <https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html>
