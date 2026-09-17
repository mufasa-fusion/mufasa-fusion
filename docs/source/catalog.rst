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

   {% set icons = {"Map": "|map-fold|", "BayesianMap": "|map-roll|"} %}
   {% for obj in objs %}
      * - {{ icons.get(obj.name, "") }}
        - :class:`~{{ obj.id }}`
        - {{ obj.summary }}
   {% endfor %}

