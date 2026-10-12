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
    "sphinx.ext.napoleon",
    "autoapi.extension",
    "custom_directives",
    "myst_nb",
]

templates_path = ['_templates']
exclude_patterns = ["_*", "**/_*"]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

rst_prolog = """\
.. |loc| image:: /../src/mufasa/graph_svg/icons/location-marker.svg
   :alt: location marker
   :class: mufasa-shape-icon
.. |obs| image:: /../src/mufasa/graph_svg/icons/observation-marker.svg
   :alt: target marker
   :class: mufasa-shape-icon
.. |map| image:: /../src/mufasa/graph_svg/icons/map-fold.svg
   :alt: foldable map
   :class: mufasa-shape-icon
.. |bmap| image:: /../src/mufasa/graph_svg/icons/map-roll.svg
   :alt: map scroll
   :class: mufasa-shape-icon
"""

autoapi_dirs = ["../src"]  # Source (code) directories
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

graphviz_output_format = "svg"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "shibuya"
html_static_path = ['_static']
html_css_files = [
    "css/shibuya-overwrite.css",
    "css/mufasa.css",
]
html_logo = "_static/img/logo/MuFASA_MuFASA.svg"
html_theme_options = {
    "accent_color": "red",
    "light_logo": html_logo,
    "dark_logo": "_static/img/logo/MuFASA_MuFASA_weiss.svg",
    "globaltoc_expand_depth": 1,
    "nav_links": [
        {"title": "Getting started", "url": "getting-started"},
        {"title": "User guide", "url": "user-guide/index"},
        {"title": "Showcases", "url": "showcases/index"},
        {"title": "Catalog", "url": "catalog"},
        {"title": "API", "url": "api/index"},
        {"title": "About", "url": "about"},
    ],
}

# Version dropdown in the header. Placeholder with a single entry until versioned builds are deployed
# (one folder per release on GitHub Pages, with the list read from a shared versions.json).
html_context = {
    "current_version": release,
    "versions": [
        (release, "https://mufasa-fusion.github.io/mufasa-fusion/"),
    ],
}
