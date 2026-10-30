---
file_format: mystnb
mystnb:
  execution_timeout: 10
---

```{code-cell}
:tags: [remove-cell]
import os.path
os.chdir(os.path.join("..", "..", "_data"))
```

# MQTT

This example sends input and output data over MQTT[^MQTT] for a more realistic scenario.
We will use the Paho[^paho_mqtt] MQTT client library, so install it with:

```bash
pip install paho-mqtt
```

## Subscriber for Inputs

Since Paho offers a push client, the input node is similar to the one defined in {ref}`push-client`.
The most notable difference is that we need to disconnect the client[{sup}`#D`](#mqtt-node)
when we want to truly stop to receiving data or else it will stay subscribed to the topic forever.

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: "def bg_thread(...): ..."
    code_prompt_hide: "def bg_thread(...):"
---
import contextlib
import threading

@contextlib.contextmanager
def bg_thread(target, *args, **kwargs):
    t = threading.Thread(target=target, args=args, kwargs=kwargs)
    t.start()
    try:
        yield
    finally:
        t.join()
```

(mqtt-node)=
```{code-cell}
from typing import Callable

from mufasa import Observation
from mufasa.io.inputs import ObservationStreamingInput

from paho.mqtt.client import Client, MQTTMessage
from paho.mqtt import subscribe

DECODER = Callable[[bytes], Observation]


class MqttInput(ObservationStreamingInput):  #1  #2
    def __init__(self, host: str, port: int, topic: str, decoder: DECODER):
        super().__init__()
        self.host = host
        self.port = port
        self.topic = topic
        self.decode = decoder

    def items(self):  #4a
        with bg_thread(subscribe.callback, self.paho_ingest_message, self.topic, 0, None, self.host, self.port):  #A
            yield from super().items()  #B

    def paho_ingest_message(self, client: Client, _, message: MQTTMessage):
        msg = message.payload
        if msg == b"END":  #C
            self.stop()
            # Disconnect the client so that the subscriber thread finishes
            client.disconnect()  #D
        else:
            self.ingest(self.decode(msg))  #3 #4b
```

Note that the message conversion is left out in the node above and delegated to a decoder function.
This is because MQTT specifies the transport, but not the structure of the message payload --
That is specific to your setup!
In this example, we assume that the payload is a GeoJSON Feature and use the following decoder function:

```{code-cell}
import json
import time

from shapely.geometry.geo import shape

_start_time = time.monotonic()


def feat_to_obs(
    raw: str | bytes, ts_k: str = "timestamp", conf_k: str = "confidence", **dfs,
) -> Observation:
    """Converts a GeoJSON Feature to a MuFASA Observation"""
    feature = json.loads(raw)
    geom = shape(feature["geometry"])
    props = dfs | feature.get("properties", {})
    # Utilize upscaled arrival timestamp for demo purposes!
    ts = props.pop(ts_k, 10 * (time.monotonic() - _start_time))
    conf = props.pop(conf_k, Observation.confidence)
    return Observation(geom, ts, props, conf)

```

## Publisher for Outputs

TODO

## Running the Example

To run this example, start a MQTT broker running in the background, for example
Eclipse Mosquitto via Docker[^mosquitto-docker]:

```bash
docker run -p 1883:1883 eclipse-mosquitto
```

To simulate a sensor, we use a simple script publishing detections as GeoJSON Features from a file.

```{code-cell}
---
tags: [hide-cell]
mystnb:
    code_prompt_show: Publisher simulating a sensor
    code_prompt_hide: Publisher simulating a sensor
---
import random

from paho.mqtt import client as mqtt

HOST = "localhost"
PORT = 1883


def sim_pub_mqtt(host: str, port: int, topic: str, file: str):
    """Publishes GeoJSON Features from a file over MQTT to simulate a server"""
    time.sleep(2)  # Startup delay (demo only)

    with open(file) as f:
        geojson = json.load(f)

    features = [json.dumps(f).encode() for f in geojson["features"]]

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.loop_start()
    try:
        client.connect(host, port)
        time.sleep(2)
        try:
            for feature in features:
                client.publish(topic, feature)
                time.sleep(.1 + .1 * random.random())
            client.publish(topic, b"END")
        finally:
            client.disconnect()
    finally:
        client.loop_stop()
```

Define a Fusion Graph.

```{code-cell}
from functools import partial

from mufasa import Graph
from mufasa.io.outputs import LocationOutput

mqtt_a = MqttInput(HOST, PORT, "sensor/a", partial(feat_to_obs, track="A"))
mqtt_b = MqttInput(HOST, PORT, "sensor/b", partial(feat_to_obs, track="B"))
mqtt_out = LocationOutput()(mqtt_a, mqtt_b)
mqtt_graph = Graph([mqtt_a, mqtt_b], [mqtt_out])

mqtt_graph.plot_graph()
```

Finally, start the sensor simulation publishers for both [`sensor_a.geojson`](/_data/sensor_a.geojson)
and [`sensor_b.geojson`](/_data/sensor_b.geojson) and run the graph.

```{code-cell}
:tags: [remove-cell]
import asyncio
import logging
from amqtt.broker import Broker

_RUNNING = True
_BROKER_READY = threading.Event()


async def _run_mqtt_broker() -> None:
    broker = Broker()
    await broker.start()
    print("MQTT broker started")
    _BROKER_READY.set()
    try:
        while _RUNNING:
            await asyncio.sleep(.5)
    finally:
        print("MQTT broker shutdown")
        await broker.shutdown()


logging.basicConfig(level=logging.FATAL)
_broker_thread = threading.Thread(target=asyncio.run, args=(_run_mqtt_broker(),))
_broker_thread.start()
_BROKER_READY.wait()
```

```{code-cell}
# Sensor threads for demo only!
with (
    bg_thread(sim_pub_mqtt, HOST, PORT, "sensor/a", "sensor_a.geojson"),
    bg_thread(sim_pub_mqtt, HOST, PORT, "sensor/b", "sensor_b.geojson"),
):
    mqtt_graph.run()

mqtt_out.result
```

```{code-cell}
:tags: [remove-cell]
_RUNNING = False
_broker_thread.join()
```

[^MQTT]: MQTT, <https://mqtt.org/>
[^paho_mqtt]: Eclipse Paho MQTT Python Client, <https://eclipse.dev/paho/files/paho.mqtt.python/html/index.html>
[^mosquitto-docker]: Eclipse Mosquitto Docker Image, Docker Hub, <https://hub.docker.com/_/eclipse-mosquitto>
