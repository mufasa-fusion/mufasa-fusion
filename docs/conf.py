import json
import os.path
import sys
from itertools import zip_longest

from autoapi import _astroid_utils
from jinja2 import Environment

import mufasa

sys.path.append(os.path.join(os.path.dirname(__file__), "_extensions"))  # Makes custom extensions importable

# Patch class docstring getter to not inherit docstrings from base classes (for API docs)
_astroid_utils.get_class_docstring = lambda node: node.doc_node.value if node.doc_node else ""


# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'mufasa-fusion'
copyright = '2026, Michael Hubner, Kilian Wohlleben, Jan Nausner, Julia Pöschl'
author = 'Michael Hubner, Kilian Wohlleben, Jan Nausner, Julia Pöschl'
release = mufasa.__version__  # Single source of truth: the package version

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "autoapi.extension",
    "custom_directives",
    "myst_nb",
    "sphinx_copybutton",
]

templates_path = ['_templates']
exclude_patterns = ["_*", "**/_*"]

nb_execution_mode = "cache"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "attrs_inline",
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

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "shibuya"
html_static_path = ['_static']
html_css_files = [
    "css/shibuya-overwrite.css",
    "css/mufasa.css",
]
html_js_files = [
    "js/versions.js",
]
html_logo = "_static/img/logo/MuFASA_MuFASA.svg"
html_theme_options = {
    "accent_color": "red",
    "light_logo": html_logo,
    "dark_logo": "_static/img/logo/MuFASA_MuFASA_weiss.svg",
    "globaltoc_expand_depth": 1,
    "github_url": "https://github.com/mufasa-fusion/mufasa-fusion",
    "nav_links": [
        {"title": "Getting started", "url": "getting-started"},
        {"title": "User guide", "url": "user-guide/index"},
        {"title": "Showcases", "url": "showcases/index"},
        {"title": "Catalog", "url": "catalog"},
        {"title": "API", "url": "api/index"},
    ],
}

# Version dropdown in the header. Each release is deployed to its own folder (see deploy-docs.yml),
# the root always shows the latest release. _static/versions.json lists all of them: add an entry per release.
# The list is written into the pages at build time; _static/js/versions.js reloads it from the site root,
# so docs of older releases also show newer versions.
with open(os.path.join(os.path.dirname(__file__), "_static", "versions.json"), encoding="utf-8") as _f:
    _versions = json.load(_f)

html_context = {
    "current_version": release,
    "versions": [(v["version"], v["url"]) for v in _versions],
}
