Node Catalog
============

.. _data-models-catalog:

Flow Data Models
----------------

.. autoapi-template::
   :context: ["|loc|", "|obs|", "|map|", "|bmap|"]

   mufasa.location.Location
   mufasa.location.Observation
   mufasa.map.Map
   mufasa.map.BayesianMap

   .. rst-class:: mufasa-node-catalog twos

   {% for obj, icon in zip(objs, ctx) %}
   - {{ icon }}

     :class:`~{{ obj.id }}`

     {{ obj.summary }}
   {% endfor %}

Processing Nodes
----------------

.. autoapi-template::
   :template: node-catalog.jinja
   :context: {
         "node_data": [
            ["|map|", "|loc|\\ /\\ |obs|"],
            ["|bmap|", "|bmap|"],
            ["|bmap|", "|bmap|"],
            ["|bmap|", "|bmap|"],
            ["|bmap|", "|bmap|"],
            ["|obs|", "|bmap|"],
            ["|loc|", "|loc|"],
            ["|loc|", "|obs|"],
            ["|obs|", "|obs|"]
         ]
      }

   mufasa.nodes.detection.threshold.Threshold
   mufasa.nodes.fusion.map_fusion.BayesianFusion
   mufasa.nodes.fusion.map_fusion.LogicalAnd
   mufasa.nodes.fusion.map_fusion.LogicalOr
   mufasa.nodes.fusion.map_fusion.MapFusion
   mufasa.nodes.mapping.pom.POM
   .. mufasa.nodes.mapping.static.StaticMap
   mufasa.nodes.tracking.dbstream.DBSTREAMClusterer
   mufasa.nodes.tracking.kalman.KalmanTracker
   mufasa.nodes.util.filter.ObservationFilter

Input Nodes
-----------

.. autoapi-template::
   :template: node-catalog.jinja
   :context: {
         "in_header_suffix": "[#InNodeCol]_",
         "node_data": [
            ["GeoJSON [#GeoJSON]_", "|loc|\\ /\\ |obs|"],
            ["GeoTIFF [#GeoTIFF]_", "|map|"],
            ["|loc|\\ /\\ |obs|", "|loc|\\ /\\ |obs|"],
            ["|map|", "|map|"],
            ["|loc|", "|loc|"],
            ["|obs|", "|obs|"],
            ["|map|", "|map|"],
            ["GeoJSON [#GeoJSON]_", "|bmap|"]
         ]
      }

   mufasa.io.inputs.geojson.GeoJsonInput
   mufasa.io.inputs.geotiff.GeoTiffInput
   mufasa.io.inputs.python_object.LocationInput
   mufasa.io.inputs.python_object.MapInput
   .. mufasa.io.inputs.streaming.StreamingInputNode
   mufasa.io.inputs.streaming.LocationStreamingInput
   mufasa.io.inputs.streaming.ObservationStreamingInput
   mufasa.io.inputs.streaming.MapStreamingInput
   mufasa.nodes.mapping.static.StaticMap

.. [#InNodeCol] Indicates the type of data they consume from external systems.
   Within the Fusion Graph, Input Nodes are sources with no incoming edges.

Output Nodes
------------

.. autoapi-template::
   :template: node-catalog.jinja
   :context: {
         "out_header_suffix": "[#OutNodeCol]_",
         "node_data": [
            ["|loc|", "GeoJSON [#GeoJSON]_"],
            ["|map|", "GeoTIFF [#GeoTIFF]_"],
            ["|loc|", "|loc|"],
            ["|map|", "|map|"],
            ["|loc|", "|loc|"],
            ["|loc|\\ / |map|", "matplotlib [#matplotlib]_"]
         ]
      }

   mufasa.io.outputs.geojson.GeoJsonOutput
   mufasa.io.outputs.geotiff.GeoTiffOutput
   mufasa.io.outputs.python_object.LocationOutput
   mufasa.io.outputs.python_object.MapOutput
   mufasa.io.outputs.streaming.StreamingOutputNode
   mufasa.io.outputs.visualization.Visualization

.. [#OutNodeCol] Indicates the type of data they deliver to external systems.
   Within the Fusion Graph, Output Nodes are terminal, so they don't have outgoing edges.

.. rubric:: References

.. [#GeoJSON] GeoJSON, see https://geojson.org
.. [#GeoTIFF] GeoTIFF, see https://www.ogc.org/standards/geotiff/
.. [#matplotlib] matplotlib, see https://matplotlib.org/
