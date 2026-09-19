"""Version and the places to look for a newer one.

Deliberately inert. The application shows these and never fetches them:
an app that phones home on launch is exactly the behaviour this tool
promises not to have, and it is also the behaviour that makes endpoint
security take an interest. Checking for an update is the operator opening
a link, in their own browser, when they choose to.
"""
from __future__ import annotations

__version__ = "0.1.3"

REPO_URL = "https://github.com/Bebop-systems/pentimento"
RELEASES_URL = f"{REPO_URL}/releases/latest"
ISSUES_URL = f"{REPO_URL}/issues"


def about() -> dict:
    return {
        "version": __version__,
        "repo": REPO_URL,
        "releases": RELEASES_URL,
        "issues": ISSUES_URL,
    }
