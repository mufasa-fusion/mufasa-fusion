---
file_format: mystnb
---

# Streaming Input Extension

## Simulating a Live Sensor

We simulate a live sensor by a TCP server that sends detections as GeoJSON Features over each connection,
one per line with a random few seconds delay in between. For convenience,
we use a context manager for starting and stopping the server that you wrap your fusion code with like so:

```python
with server_thread(ADDRESS, FeatureSendingRequestHandler):
    graph.run()
```

:::{important}
In a real-world scenario, you don't need something equivalent! You certainly have an externally managed sensor.
Within the fusion code, you'd take it for granted that the system is up and running.
:::

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

with open("sensor_a.geojson") as features_file:
    features = json.load(features_file)["features"]

features_bin = [json.dumps(f).encode() + SEP for f in features]

class FeatureSendingRequestHandler(socketserver.BaseRequestHandler):
    """Simulates a sensor that is sending GeoJSON Feature lines"""

    def handle(self):
        for feature in features_bin:
            self.request.sendall(feature)
            time.sleep(1 + random.random())


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

(common-basics)=
## Integration Basics

To use that sensor in fusion systems, we extend MUFASA with a custom {class}`~mufasa.io.inputs.base.InputNode` subclass.
They are responsible for connecting to the data streams of external systems and for converting them to
MuFASA's own data models. And since it is a live sensor -- and we want continuous updates to our outputs[^no_stream_out]
-- we implement a streaming one derived from {class}`~mufasa.io.inputs.streaming.StreamingInputNode`.

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
            ts_col: str = "timestamp",
            conf_col: str = "confidence",
            props_default: dict[str, "Any"] | None = None,
    ):
        super().__init__()
        self.ts_col = ts_col
        self.conf_col = conf_col
        self.props_default = props_default if props_default is not None else {}

    def feature_to_observation(self, feature_str: str) -> Observation:  #3
        """Converts a GeoJSON Feature to a MuFASA Observation"""
        feature = json.loads(feature_str)
        geom = shape(feature["geometry"])
        props = self.props_default | feature.get("properties", {})
        # Utilize arrival timestamp for demo purposes!
        ts = props.pop(self.ts_col, time.monotonic() - _start_time)
        conf = props.pop(self.conf_col, Observation.confidence)
        return Observation(geom, ts, props, conf)

    def get_config(self) -> dict:  #4
        return {
            "ts_col": self.ts_col,
            "conf_col": self.conf_col,
            "props_default": self.props_default
        }
```

The key points are:

[{sup}`#1`](#basic-node)
: Derives from {class}`~mufasa.io.inputs.streaming.StreamingInputNode` to signal to the {class}`~mufasa.graph.Graph`
  that it is doing blocking calls to wait for new messages.

[{sup}`#2`](#basic-node)
: Specifies its `_output_type` as {class}`~mufasa.location.Observation`.

[{sup}`#3`](#basic-node)
: Provides a conversion from raw messages to a MuFASA data type.  
  We will use it later in the push/pull subclasses.

[{sup}`#4`](#basic-node)
: Defines its config in `get_config()` to support exporting fusion architectures.  
  Later, we will register concrete subclasses to the {attr}`~mufasa.registry.NODE_REGISTRY` for imports.

Another key point is still missing: the connection to the sensor.
For that, you usually leverage a client library specific to your data transport
-- and they come in two fashions: as {ref}`push <push-client>` or {ref}`pull <pull-client>` architectures.

(pull-client)=
## Integrating Pull Clients

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

To integrate it, we overwrite {func}`~mufasa.io.inputs.streaming.StreamingInputNode.items()`[{sup}`#1`](#pull-node)
so that it yields the messages from the generator after conversion.
We derive the input node from the one developed in {ref}`common-basics`[{sup}`#2`](#pull-node)
to inherit conversion and config logic and also register the node for imports[{sup}`#3`](#pull-node).

(pull-node)=
```{code-cell}
from mufasa.registry import NODE_REGISTRY

class GeoJsonObservationPullInput(GeoJsonObservationStreamingInput):  #2
    def __init__(self, address: tuple[str, int], **kwargs):
        super().__init__(**kwargs)
        self.address = address

    def items(self):  #1
        for line in sock_recv_lines(self.address):
            yield self.feature_to_observation(line)

    def get_config(self) -> dict:
        return {"address": self.address, **super().get_config()}

NODE_REGISTRY[GeoJsonObservationPullInput.__name__] = GeoJsonObservationPullInput  #3
```

Usage:

```{code-cell}
from mufasa import Graph
from mufasa.io.outputs import LocationOutput

pull_a = GeoJsonObservationPullInput(ADDRESS, props_default={"track": "A"})
pull_b = GeoJsonObservationPullInput(ADDRESS, props_default={"track": "B"})
out_pull = LocationOutput()(pull_a, pull_b)

with server_thread(ADDRESS, FeatureSendingRequestHandler):  # Demo only!
    graph = Graph([pull_a, pull_b], [out_pull])
    graph.run()
```

:::{todo}
The `Graph` constructor already needs the server running! Why?

It's `_configure_run()` calls the nodes `items()` (and that is the one connecting).
It is called at the end of __init__ and not at the beginning of `run()` -- is this really necessary?
:::

```{code-cell}
graph.plot_graph()
```

```{code-cell}
out_pull.result
```

(push-client)=
## Integrating Push Clients

Push clients have their own blocking loops that push each message received to a user-supplied callback function.

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

To integrate them, we run the loop on a background thread[{sup}`#1`](#push-usage) and use
{func}`~mufasa.io.inputs.streaming.StreamingInputNode.ingest` in the callback function[{sup}`#2`](#push-node)
to forward the data to MuFASA. This implementation uses a dedicated end message to trigger
{func}`~mufasa.io.inputs.streaming.StreamingInputNode.stop`[{sup}`#4`](#push-node) what indicates the data stream's end.
We derive the input node from the one developed in {ref}`common-basics`[{sup}`#3`](#push-node)
to inherit conversion and config logic and also register the node for imports[{sup}`#5`](#push-node).

(push-node)=
```{code-cell}
class GeoJsonObservationPushInput(GeoJsonObservationStreamingInput):  #3
    END_MSG = "END"

    def ingest_feature_str(self, feature_str: str) -> None:
        if feature_str == self.END_MSG:
            self.stop()  #4
        else:
            self.ingest(self.feature_to_observation(feature_str))  #2

    def ingest_feature_bin(self, feature_bin: str) -> None:
        self.ingest_feature_str(feature_bin.decode())

NODE_REGISTRY[GeoJsonObservationPushInput.__name__] = GeoJsonObservationPushInput
```

Usage:

```{code-cell}
push_a = GeoJsonObservationPushInput(props_default={"track": "A"})
push_b = GeoJsonObservationPushInput(props_default={"track": "B"})
out_push = LocationOutput()(push_a, push_b)
graph = Graph([push_a, push_b], [out_push])

graph.plot_graph()
```

(push-usage)=
```{code-cell}
with (
    server_thread(ADDRESS, FeatureSendingRequestHandler),  # Demo only!
    # Start reception loops outside MuFASA and pass callbacks that ingest()  #1
    on_bg_thread(sock_recv_loop, ADDRESS, push_a.ingest_feature_str, push_a.END_MSG),
    on_bg_thread(sock_recv_loop, ADDRESS, push_b.ingest_feature_str, push_b.END_MSG),
):
    graph.run()

out_push.result
```

[^socketserver_examples]: Python Standard Library, `socketserver` module's examples,
<https://docs.python.org/3/library/socketserver.html#examples>
[^no_stream_out]: Assuming we would use streaming-capable output nodes, too -- What we don't do in this demo.
