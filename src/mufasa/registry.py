"""Node registry: maps type-name strings to their classes.

Used by Graph.from_config() to reconstruct nodes from a serialized config.
Register new node types here to make them deserializable.
"""
from mufasa.nodes.mapping.pom import POM
from mufasa.nodes.mapping.static import StaticMap
from mufasa.nodes.fusion.map_fusion import BayesianFusion, LogicalAnd, LogicalOr
from mufasa.nodes.detection.threshold import Threshold
from mufasa.nodes.util.filter import ObservationFilter
from mufasa.nodes.tracking.kalman import KalmanTracker
from mufasa.nodes.tracking.dbstream import DBSTREAMClusterer
from mufasa.io.inputs.geojson import GeoJsonInput
from mufasa.io.inputs.geotiff import GeoTiffInput
from mufasa.io.outputs.geojson import GeoJsonOutput
from mufasa.io.outputs.geotiff import GeoTiffOutput
from mufasa.io.outputs.python_object import LocationOutput, MapOutput
from mufasa.io.outputs.visualization import Visualization

NODE_REGISTRY: dict[str, type] = {
    "POM":               POM,
    "StaticMap":         StaticMap,
    "BayesianFusion":    BayesianFusion,
    "LogicalAnd":        LogicalAnd,
    "LogicalOr":         LogicalOr,
    "Threshold":            Threshold,
    "ObservationFilter": ObservationFilter,
    "KalmanTracker":      KalmanTracker,
    "DBSTREAMClusterer":  DBSTREAMClusterer,
    "GeoJsonInput":      GeoJsonInput,
    "GeoTiffInput":      GeoTiffInput,
    "GeoJsonOutput":     GeoJsonOutput,
    "GeoTiffOutput":     GeoTiffOutput,
    "LocationOutput":    LocationOutput,
    "MapOutput":         MapOutput,
    "Visualization":     Visualization,
}
