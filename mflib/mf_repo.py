"""
Which MeasurementFramework code a measurement node clones.

By default mflib clones the MeasurementFramework release that GitHub labels
"Latest", looked up when the node is set up. A newer MF release is picked up
without a new mflib release. Any branch or tag name can be passed instead
(e.g. ``"main"`` or ``"v1.0.6"``) to bypass the lookup.
"""
import urllib.request

MF_REPO_URL = "https://github.com/fabric-testbed/MeasurementFramework.git"

#: Sentinel ref meaning "the release GitHub labels Latest".
LATEST = "latest"

#: Used when the Latest release cannot be looked up (e.g. GitHub unreachable).
FALLBACK_REF = "main"

# The web redirect (not the REST API) is used because the API allows only
# 60 unauthenticated requests per hour per IP, which a shared JupyterHub
# could exhaust. /releases/latest redirects to /releases/tag/<tag>.
MF_LATEST_RELEASE_URL = "https://github.com/fabric-testbed/MeasurementFramework/releases/latest"


def latest_mf_release(timeout=10):
    """Tag of the MeasurementFramework release GitHub labels Latest, or None if it can't be determined."""
    try:
        req = urllib.request.Request(MF_LATEST_RELEASE_URL, method="HEAD", headers={"User-Agent": "mflib"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.url
    except Exception:
        return None
    marker = "/releases/tag/"
    return final_url.split(marker, 1)[1].strip("/") if marker in final_url else None


def resolve_mf_ref(ref=LATEST, verbose=True):
    """Turn ``"latest"`` (or None) into the current Latest release tag; other refs pass through unchanged."""
    if ref and ref != LATEST:
        return ref
    tag = latest_mf_release()
    if tag:
        if verbose:
            print(f"MeasurementFramework: using latest release {tag}")
        return tag
    if verbose:
        print(f"MeasurementFramework: could not look up the latest release; using {FALLBACK_REF!r}")
    return FALLBACK_REF
