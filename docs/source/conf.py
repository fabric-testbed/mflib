# 
import pathlib
import sys
sys.path.insert(0, pathlib.Path(__file__).parents[2].resolve().as_posix())

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'MFLib'
copyright = '2023, Fabric UKY Team'
author = 'Fabric UKY Team'

import mflib

release = mflib.__version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'myst_parser',
    'sphinx.ext.napoleon',
    'sphinxcontrib.inkscapeconverter',
]

templates_path = ['_templates']
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

#html_theme = 'alabaster'
# to use furo theme "pip install furo"
html_theme = "furo"
html_static_path = ['_static']

latex_elements = {
    'extraclassoptions': 'openany,oneside',
    'sphinxsetup': 'iconpackage=none',
}
