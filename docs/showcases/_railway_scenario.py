"""Synthetic replica of the railway security showcase: a group committing graffiti.

Follows the scenario "group committing graffiti" of Hubner et al., Sensors 2024 (doi:10.3390/s24134118): a sprayer
and a lookout walk from the station (1) along the tracks, chatting and rattling their spray cans (2), cross the
tracks (3), split up to spray a wagon (4) and keep watch (5), and finally flee back to the station (6).

The site geometry follows the trial (a 150 m x 30 m region of interest with the sensor station at one end), placed
along an arbitrary, neutral stretch of open line and rotated to follow it. The detections are invented, roughly
1/50 of the trial's amounts, but mimic the sensors:

- Thermal: two cameras (wide angle up to 11 m, telephoto from 9 m), detecting reliably by day and night. Their
  overlap produces duplicate detections. Footprints grow longer and less precise with distance.
- Radar: 1 m circles, only for targets moving towards or away from it; targets crossing the tracks or standing
  still are not detected.
- Acoustic: direction only, so triangles of 30 m range from every sensor within reach of the sound.

Deterministic (fixed random seed). Run ``write(folder)`` to regenerate the files.
"""

import json
import math
import random
from pathlib import Path

from mufasa import BoundingBox

# --- Site, in a local frame: x along the track (0..150 m), y across it (-15..15 m, to the left of x) ---------

CENTER = (16.8397835, 48.2527829)  # Site center between the two tracks of an open line (lon, lat)
ANGLE_DEG = 4.51                   # Direction of the track (local x axis), counter-clockwise from east
LENGTH, WIDTH = 150.0, 30.0
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(CENTER[1]))

STATION = (0.0, -5.0)  # Thermal cameras and radar, at the building at the western end
ACOUSTIC_SENSORS = [(25.0, 0.0), (70.0, 0.0), (115.0, 0.0)]
TRACKS_Y = [-7.5, 0.0, 7.5]
WAGON = (115.0, 135.0, -4.0)  # x from, x to, y: the wagon to be sprayed, between two tracks

CAMERA_WIDE_MAX_M = 11.0  # The wide-angle camera sees up to here ...
CAMERA_TELE_MIN_M = 9.0   # ... the telephoto camera from here on: in between, both see the target
ACOUSTIC_RANGE_M = 30.0

# Keyframes per person: (time in s, x, y)
POSITIONS = {1: (2, -8), 2: (45, -3), 3: (100, 9), 4: (125, -3), 5: (100, 3), 6: (2, -12)}
SPRAYER = [(0, *POSITIONS[1]), (32, *POSITIONS[2]), (55, 95, -3), (63, *POSITIONS[3]), (72, *POSITIONS[4]),
           (110, *POSITIONS[4]), (145, *POSITIONS[6])]
LOOKOUT = [(0, 3, -9.5), (32, 46, -4.5), (55, 96, -4.5), (63, 101, 10), (69, *POSITIONS[5]),
           (110, *POSITIONS[5]), (143, 3, -13)]
CHATTING = (32, 63)  # Chatting and rattling cans, from (2) until they separate at (3)
SPRAYING = (72, 110)
DURATION = 145

def to_lonlat(x: float, y: float) -> list[float]:
    """Local metres to WGS84 (lon, lat): rotate the site to follow the track, then place it at CENTER."""
    a = math.radians(ANGLE_DEG)
    east = (x - LENGTH / 2) * math.cos(a) - y * math.sin(a)
    north = (x - LENGTH / 2) * math.sin(a) + y * math.cos(a)
    return [CENTER[0] + east / M_PER_DEG_LON, CENTER[1] + north / M_PER_DEG_LAT]


# The bounding box around the rotated region of interest
_CORNERS = [to_lonlat(x, y) for x in (0, LENGTH) for y in (-WIDTH / 2, WIDTH / 2)]
BBOX = BoundingBox(min(c[0] for c in _CORNERS), min(c[1] for c in _CORNERS),
                   max(c[0] for c in _CORNERS), max(c[1] for c in _CORNERS))


def position(keyframes, t: float) -> tuple[float, float]:
    """Linear interpolation between keyframes."""
    for (t0, x0, y0), (t1, x1, y1) in zip(keyframes, keyframes[1:]):
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return x0 + f * (x1 - x0), y0 + f * (y1 - y0)
    return keyframes[-1][1:]


def velocity(keyframes, t: float, dt: float = 0.5) -> tuple[float, float]:
    (x0, y0), (x1, y1) = position(keyframes, t - dt), position(keyframes, t + dt)
    return (x1 - x0) / (2 * dt), (y1 - y0) / (2 * dt)


# --- Detections -------------------------------------------------------------------------------------------------

def _feature(ring_xy, t, confidence, label) -> dict:
    return {"type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[to_lonlat(x, y) for x, y in ring_xy]]},
            "properties": {"timestamp": round(t, 2), "confidence": round(confidence, 3), "label": label}}


def _footprint(x, y, distance) -> list:
    """Ground projection of a thermal bounding box: elongated along the viewing ray, longer when far away."""
    length, width = 1.0 + 0.03 * distance, 0.8
    ux, uy = (x - STATION[0]) / distance, (y - STATION[1]) / distance  # Unit vector along the ray
    corners = [(-length / 2, -width / 2), (length / 2, -width / 2), (length / 2, width / 2), (-length / 2, width / 2)]
    ring = [(x + a * ux - b * uy, y + a * uy + b * ux) for a, b in corners]
    return ring + ring[:1]


def _circle(x, y, radius, points=12) -> list:
    return [(x + radius * math.cos(2 * math.pi * i / points), y + radius * math.sin(2 * math.pi * i / points))
            for i in range(points + 1)]


def _sector(sensor, bearing, opening) -> list:
    """Triangle from a sensor in the direction of a sound, with ACOUSTIC_RANGE_M range."""
    sx, sy = sensor
    edges = [bearing - opening / 2, bearing + opening / 2]
    return [(sx, sy), *((sx + ACOUSTIC_RANGE_M * math.cos(a), sy + ACOUSTIC_RANGE_M * math.sin(a)) for a in edges),
            (sx, sy)]


def thermal(rng: random.Random) -> list[dict]:
    features = []
    for person in (SPRAYER, LOOKOUT):
        t = rng.uniform(0, 0.6)
        while t < DURATION:
            x, y = position(person, t)
            distance = math.dist((x, y), STATION)
            cameras = [d for d, sees in (("wide", distance <= CAMERA_WIDE_MAX_M), ("tele", distance >= CAMERA_TELE_MIN_M)) if sees]
            for _ in cameras:  # In the overlap, both cameras report the person
                sigma = 0.2 + 0.01 * distance
                nx, ny = x + rng.gauss(0, sigma), y + rng.gauss(0, sigma)
                confidence = min(0.95, max(0.5, rng.gauss(0.88 - 0.001 * distance, 0.04)))
                features.append(_feature(_footprint(nx, ny, math.dist((nx, ny), STATION)), t, confidence, "person"))
            t += rng.uniform(0.45, 0.75)  # About 1.7 Hz per person
    return features


def radar(rng: random.Random) -> list[dict]:
    features = []
    for person in (SPRAYER, LOOKOUT):
        t = rng.uniform(0, 1)
        while t < DURATION:
            x, y = position(person, t)
            vx, vy = velocity(person, t)
            speed = math.hypot(vx, vy)
            rx, ry = x - STATION[0], y - STATION[1]
            radial = abs(vx * rx + vy * ry) / (speed * math.hypot(rx, ry)) if speed > 0 else 0
            if speed > 0.3 and radial > 0.5:  # Only movement towards or away from the radar reflects
                nx, ny = x + rng.gauss(0, 0.5), y + rng.gauss(0, 0.5)
                features.append(_feature(_circle(nx, ny, 1.0), t, rng.uniform(0.6, 0.8), "unknown"))
            t += rng.uniform(1.6, 2.4)
    return features


def acoustic(rng: random.Random) -> list[dict]:
    events = [(t, SPRAYER, rng.choice(["speech", "rattle"])) for t in (36, 44, 52, 60)]
    events += [(t, person, "speech") for t, person in ((65, SPRAYER), (69, LOOKOUT))]  # Talking on the way to the train
    events += [(t, SPRAYER, "vandalism") for t in (76, 86, 96, 106)]
    features = []
    for t, person, label in events:
        x, y = position(person, t)
        for sensor in ACOUSTIC_SENSORS:
            if math.dist((x, y), sensor) <= ACOUSTIC_RANGE_M:
                bearing = math.atan2(y - sensor[1], x - sensor[0]) + math.radians(rng.gauss(0, 5))
                opening = math.radians(rng.uniform(12, 25))
                features.append(_feature(_sector(sensor, bearing, opening), t, rng.uniform(0.6, 0.9), label))
    return features


def ground_truth() -> dict[str, list[tuple[float, float]]]:
    """True paths of both people in the local frame, sampled every second."""
    return {name: [position(keys, t) for t in range(DURATION + 1)] for name, keys in (("sprayer", SPRAYER), ("lookout", LOOKOUT))}


def write(folder) -> dict[str, str]:
    """Write one GeoJSON file per sensor into ``folder``; returns their paths by name."""
    rng = random.Random(7)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, features in (("thermal", thermal(rng)), ("radar", radar(rng)), ("acoustic", acoustic(rng))):
        features.sort(key=lambda f: f["properties"]["timestamp"])
        paths[name] = str(folder / f"{name}.geojson")
        Path(paths[name]).write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return paths
