"""Google Maps Platform preview URL builders.

Builds ready-to-embed thumbnail URLs for Street View Static and
Maps Static for a given ``(lat, lon)``. The API key is read from the
``GOOGLE_MAPS_API_KEY`` environment variable. If the key is missing,
all functions return ``None`` so the renderer degrades gracefully
without breaking the HTML output.
"""

from __future__ import annotations

import os
from urllib.parse import urlencode

ENV_VAR = "GOOGLE_MAPS_API_KEY"

# Thumbnail sizing (kept small so <img> tags stay lightweight).
STREETVIEW_SIZE = "320x200"
STATICMAP_SIZE = "320x200"
STATICMAP_ZOOM = 19
STATICMAP_TYPE = "hybrid"  # satellite + road labels

_STREETVIEW_ENDPOINT = "https://maps.googleapis.com/maps/api/streetview"
_STATICMAP_ENDPOINT = "https://maps.googleapis.com/maps/api/staticmap"


def get_api_key() -> str | None:
    """Return the API key from the environment, or ``None`` if unset/blank."""
    key = os.environ.get(ENV_VAR, "").strip()
    return key or None


def streetview_url(lat: float, lon: float, api_key: str | None = None) -> str | None:
    """Build a Street View Static thumbnail URL for a coordinate.

    Returns ``None`` if no API key is available. The resulting URL embeds
    the key as a query parameter, so it can be used directly in an
    ``<img src=...>`` tag.
    """
    key = api_key if api_key is not None else get_api_key()
    if not key:
        return None
    params = {
        "size": STREETVIEW_SIZE,
        "location": f"{lat:.6f},{lon:.6f}",
        "fov": 90,
        "key": key,
    }
    return f"{_STREETVIEW_ENDPOINT}?{urlencode(params)}"


def staticmap_url(lat: float, lon: float, api_key: str | None = None) -> str | None:
    """Build a Maps Static satellite thumbnail URL for a coordinate.

    Returns ``None`` if no API key is available.
    """
    key = api_key if api_key is not None else get_api_key()
    if not key:
        return None
    params = {
        "center": f"{lat:.6f},{lon:.6f}",
        "zoom": STATICMAP_ZOOM,
        "size": STATICMAP_SIZE,
        "maptype": STATICMAP_TYPE,
        "markers": f"color:red|{lat:.6f},{lon:.6f}",
        "key": key,
    }
    return f"{_STATICMAP_ENDPOINT}?{urlencode(params)}"


def gmaps_link(lat: float, lon: float) -> str:
    """Return a plain google.com/maps deep link. Does NOT require a key."""
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"


def preview_cell_html(lat: float, lon: float) -> str:
    """Render the complete `<td>` inner HTML for a stop preview cell.

    Shows Street View + satellite thumbnails side by side when the API
    key is available. When the key is missing (or lat/lon are None),
    falls back to a plain "Ver en Maps" text link.
    """
    if lat is None or lon is None:
        return "-"

    link = gmaps_link(lat, lon)
    sv = streetview_url(lat, lon)
    sat = staticmap_url(lat, lon)

    if not sv and not sat:
        return f"<a href='{link}' target='_blank' rel='noopener'>Ver en Maps</a>"

    parts = ["<div style='display:flex;gap:4px;align-items:center;'>"]
    if sv:
        parts.append(
            f"<a href='{link}' target='_blank' rel='noopener' title='Street View'>"
            f"<img src='{sv}' alt='Street View' "
            "style='width:80px;height:50px;object-fit:cover;border-radius:4px;border:1px solid #e2e8f0;'>"
            "</a>"
        )
    if sat:
        parts.append(
            f"<a href='{link}' target='_blank' rel='noopener' title='Satelite'>"
            f"<img src='{sat}' alt='Satelite' "
            "style='width:80px;height:50px;object-fit:cover;border-radius:4px;border:1px solid #e2e8f0;'>"
            "</a>"
        )
    parts.append("</div>")
    return "".join(parts)
