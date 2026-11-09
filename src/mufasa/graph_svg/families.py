"""Data type families: how ports and edges are colored and which icon they show.

To add a family, add its root data class with a color and an icon file (in ``icons/``) to ``FAMILIES``.
Subclasses of the root belong to the family automatically.
"""

from dataclasses import dataclass

from mufasa.location import Location, Observation
from mufasa.map import BayesianMap, Map


@dataclass(frozen=True)
class Family:
    root: type
    color: str
    icon: str  # File name in icons/, without .svg


FAMILIES = [
    Family(Location, "#31b7bc", "location-marker"),
    Family(Map, "#470f51", "map-fold"),
]

UNKNOWN_FAMILY = Family(object, "#8a9196", "unknown")

# Icons for subtypes; types without an entry show the icon of their closest ancestor listed here or in FAMILIES
TYPE_ICONS = {
    Observation: "observation-marker",
    BayesianMap: "map-roll",
}


def family_of(data_type: type) -> Family:
    return next((family for family in FAMILIES if issubclass(data_type, family.root)), UNKNOWN_FAMILY)


def icon_of(data_type: type) -> str:
    """The most specific icon: the type's own, else its closest ancestor's, else its family's."""
    return next((TYPE_ICONS[cls] for cls in data_type.__mro__ if cls in TYPE_ICONS), family_of(data_type).icon)
