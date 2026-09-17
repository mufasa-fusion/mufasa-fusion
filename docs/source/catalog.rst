Catalog
=======

Edge Data Types
---------------

.. autoapi-template::

   mufasa.location.Location
   mufasa.location.Observation
   mufasa.map.Map
   mufasa.map.BayesianMap

   .. list-table::

   {% set icons = {"Location": "|loc|", "Observation": "|obs|", "Map": "|map|", "BayesianMap": "|bmap|"} %}
   {% for obj in objs %}
      * - {{ icons.get(obj.name, "") }}
        - :class:`~{{ obj.id }}`
        - {{ obj.summary }}
   {% endfor %}

Processing Nodes
----------------

Input Nodes
-----------

.. autoapi-template::

   mufasa.io.inputs.geojson.GeoJsonInput
   mufasa.io.inputs.geotiff.GeoTiffInput
   mufasa.io.inputs.python_object.LocationInput
   mufasa.io.inputs.python_object.MapInput
   .. mufasa.io.inputs.streaming.StreamingInputNode
   mufasa.io.inputs.streaming.LocationStreamingInput
   mufasa.io.inputs.streaming.ObservationStreamingInput
   mufasa.io.inputs.streaming.MapStreamingInput

   .. list-table::
      :header-rows: 1

      * - In [#InNodeCol]_
        - Out
        - Stream
        - Name
        - Summary
   {% for obj, (in, out) in zip(objs, [
      ("GeoJSON [#GeoJSON]_", "|loc|\ /\ |obs|"),
      ("GeoTIFF [#GeoTIFF]_", "|map|"),
      ("|loc|\ /\ |obs|", "|loc|\ /\ |obs|"),
      ("|map|", "|map|"),
      ("|loc|", "|loc|"),
      ("|obs|", "|obs|"),
      ("|map|", "|map|"),
   ]) %}
      * - {{ in }}
        - {{ out }}
        - {{ "yes" if "StreamingInputNode" in obj.bases else "--" }}
        - :class:`~{{ obj.id }}`
        - {{ obj.summary }}
   {% endfor %}

.. [#InNodeCol] Indicates the type of data they consume from external systems.
   Within the Fusion Graph, Input Nodes are sources with no incoming edges.

Output Nodes
------------

.. autoapi-template::

   mufasa.io.outputs.geojson.GeoJsonOutput
   mufasa.io.outputs.geotiff.GeoTiffOutput
   mufasa.io.outputs.python_object.LocationOutput
   mufasa.io.outputs.python_object.MapOutput
   mufasa.io.outputs.streaming.StreamingOutputNode
   mufasa.io.outputs.visualization.Visualization

   .. list-table::
      :header-rows: 1

      * - In
        - Out [#OutNodeCol]_
        - Stream
        - Name
        - Summary
   {% for obj, (in, out, stream) in zip(objs, [
      ("|loc|", "GeoJSON [#GeoJSON]_", False),
      ("|map|", "GeoTIFF [#GeoTIFF]_", False),
      ("|loc|", "|loc|", False),
      ("|map|", "|map|", False),
      ("|loc|", "|loc|", True),
      ("|loc|\ /\ |map|", "matplotlib [#matplotlib]_", True),
   ]) %}
      * - {{ in }}
        - {{ out }}
        - {{ "yes" if stream else "--" }}
        - :class:`~{{ obj.id }}`
        - {{ obj.summary }}
   {% endfor %}

.. [#OutNodeCol] Indicates the type of data they deliver to external systems.
   Within the Fusion Graph, Output Nodes are terminal, so they don't have outgoing edges.

.. rubric:: References

.. [#GeoJSON] GeoJSON, see https://geojson.org
.. [#GeoTIFF] GeoTIFF, see https://www.ogc.org/standards/geotiff/
.. [#matplotlib] matplotlib, see https://matplotlib.org/
