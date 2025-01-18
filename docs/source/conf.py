# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "snap-python"
copyright = "2025, Alexander Lukens"
author = "Alexander Lukens"

# get release from pyproject.toml
from toml import load

with open("../../pyproject.toml", "r") as f:
    pyproject = load(f)

release = pyproject["tool"]["poetry"]["version"]
version = f"v{release}"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc", "sphinx.ext.githubpages"]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"

html_theme_options = {
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "vcs_pageview_mode": "",
    "flyout_display": "hidden",
    "version_selector": True,
    "language_selector": True,
    # Toc options
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
}

html_static_path = ["_static"]

# Add the "Edit on GitHub" button
html_context = {
    "display_github": True,  # Integrate GitHub
    "github_user": "alexdlukens",  # Username
    "github_repo": "snap-python",  # Repo name
    "github_version": "master",  # Version
    "conf_py_path": "/docs/source/",  # Path in the checkout to the docs root
}
github_url = "https://github.com/alexdlukens/snap-python/"
