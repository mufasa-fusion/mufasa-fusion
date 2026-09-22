import os.path
import sys
from itertools import zip_longest

from jinja2 import Environment

sys.path.append(os.path.join(os.path.dirname(__file__), "_extensions"))  # Makes custom extensions importable

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'mufasa-fusion'
copyright = '2026, Michael Hubner, Kilian Wohlleben, Jan Nausner, Julia Pöschl'
author = 'Michael Hubner, Kilian Wohlleben, Jan Nausner, Julia Pöschl'
release = '0.1.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'myst_parser',
    "sphinx.ext.napoleon",
    "autoapi.extension",
    "custom_directives",
]

templates_path = ['_templates']
exclude_patterns = []

rst_prolog = """\
.. |loc| image:: /images/shapes/location-marker.svg
   :alt: location marker
   :class: mufasa-shape-icon
.. |obs| image:: /images/shapes/observation-marker.svg
   :alt: target marker
   :class: mufasa-shape-icon
.. |map| image:: /images/shapes/map-fold.svg
   :class: mufasa-shape-icon
   :alt: foldable map
.. |bmap| image:: /images/shapes/map-roll.svg
   :alt: map scroll
   :class: mufasa-shape-icon
"""

autoapi_dirs = ["../../src"]  # Source (code) directories
autoapi_root = "api"  # Target documentation directory
autoapi_template_dir = "_templates/api"
autoapi_python_class_content = "both"  # Append init docs to class docs (since init isn't shown separately)
autodoc_typehints = "both"  # In signatures and parameter description
# autoapi_add_toctree_entry = False
autoapi_keep_files = True
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
    "special-members"
    # "imported-members",
]

def autoapi_prepare_jinja_env(env: Environment):
    env.globals["zip"] = zip_longest

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "shibuya"
html_static_path = ['_static']
html_css_files = [
    "css/theme-overwrite.css",
    "css/custom.css",
]
html_theme_options = {
    "accent_color": "red",
    "globaltoc_expand_depth": 1,
    "light_logo": "_static/img/logo/MuFASA_MuFASA.svg",
    "dark_logo": "_static/img/logo/MuFASA_MuFASA_weiss.svg",
}
