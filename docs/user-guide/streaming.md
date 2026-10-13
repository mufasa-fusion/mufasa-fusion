---
file_format: mystnb
---

# Streaming Input Extension

## Simulating a Live Sensor

We simulate a live sensor by a TCP server that sends detections as GeoJSON Features over each connection,
one per line with a random 1 to 2 seconds delay in between.

Its main components are:

- a `BaseRequestHandler` implementation `FeatureSendingRequestHandler` that sends GeoJSON Features
- a context manager `server_thread` that starts the TCP server on a separate thread and shuts it down on exit
- a generator function `sock_recv_lines` yielding lines of text received from a client socket

The TCP code is largely based on Python's official `socketserver` examples[^socketserver_examples].

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

# Allow reusing the same port immediately after server shutdown (for repeated calls)
socketserver.ThreadingTCPServer.allow_reuse_address = True

@contextlib.contextmanager
def server_thread(address: tuple[str, int], handler: socketserver.BaseRequestHandler):
    """Starts a sensor server on a separate thread on enter and shuts it down on exit"""
    with socketserver.ThreadingTCPServer(address, handler) as server:
        server_thread = threading.Thread(target=server.serve_forever)
        try:
            server_thread.start()
            yield
        finally:
            server.shutdown()
            server_thread.join()


# sock_recv_lines

import random
import socket

def sock_recv_lines(address: tuple[str, int]):
    """Yields lines of text received from a socket connected to the given address"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect(address)
        yield from sock.makefile()
```

Here is how you would use these snippets outside MuFASA:

```{code-cell}
ADDRESS = "localhost", 8000

with server_thread(ADDRESS, FeatureSendingRequestHandler):
    for line in sock_recv_lines(ADDRESS):
            print(f"[client] received data:", line)
```

## Integration in MuFASA

To connect that sensor to a fusion system, we extend MUFASA with a custom
{class}`~mufasa.io.inputs.streaming.StreamingInputNode` subclass.

:::{todo}
- Explain what `_output_type`, `items()`, and `get_config()` do
- The registry!
:::

```{code-cell}
from mufasa.location import Observation
from mufasa.io.inputs import StreamingInputNode
from shapely.geometry.geo import shape

class SocketObservationInput(StreamingInputNode):
    _output_type = Observation

    def __init__(
            self,
            address: tuple[str, int],
            ts_col: str = "timestamp",
            conf_col: str = "confidence",
            fill_conf: float = Observation.confidence,
    ):
        super().__init__()
        self.address = address
        self.ts_col = ts_col
        self.conf_col = conf_col
        self.fill_conf = fill_conf

    def items(self):
        for line in sock_recv_lines(self.address):
            feature = json.loads(line)
            geom = shape(feature["geometry"])
            props = dict(feature.get("properties") or {})
            ts = props.get(self.ts_col, 0)
            conf = props.pop(self.conf_col, self.fill_conf)
            yield Observation(geom, ts, props, conf)

    def get_config(self) -> dict:
        return {
            "address": self.address,
            "ts_col": self.ts_col,
            "conf_col": self.conf_col,
            "fill_conf": self.fill_conf
        }
```

:::{todo}
This ignores `StreamingInputNode`s `_queue`, `ingest()` function and `items()` implementation completely!
But I can't imagine how to use them. Where would the main loop, that receives data and calls `ingest()` with it, live?
:::

```{code-cell}
from mufasa import Graph
from mufasa.io.outputs import LocationOutput

inp = SocketObservationInput(ADDRESS)
out = LocationOutput()(inp)

with server_thread(ADDRESS, FeatureSendingRequestHandler):
    graph = Graph([inp], [out])
    graph.run()
```

It takes a while until {func}`~mufasa.graph.Graph.run` finishes because the data arrives with a few seconds delay.

:::{todo}
The `Graph` constructor already needs the server running! Why?

It's `_configure_run()` calls the nodes `items()` (and that is the one connecting). It is called at the end of __init__ and not at the beginning of `run()` -- is this really necessary?
:::

```{code-cell}
graph.plot_graph()
```

```{code-cell}
out.result
```

[^socketserver_examples]: Python Standard Library, `socketserver` module's examples,
<https://docs.python.org/3/library/socketserver.html#examples>
