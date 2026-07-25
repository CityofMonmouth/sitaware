from datetime import datetime, timedelta

import requests

import os
from datetime import datetime, timedelta

import requests

# Every deployment needs its own values here — these are NOT meant to work
# out of the box for anyone but Monmouth, IL. Set WEATHER_LAT/WEATHER_LON,
# RADAR_STATION_ID, and NWS_CONTACT_EMAIL in .env for your own location.
# Defaults below are Monmouth, IL's real values, kept only so a fresh clone
# doesn't crash before it's configured — not a recommendation to use them.
LAT = float(os.environ.get("WEATHER_LAT", "40.9106"))
LON = float(os.environ.get("WEATHER_LON", "-90.6482"))
RADAR_STATION = os.environ.get("RADAR_STATION_ID", "KDVN")

# NWS API requires a descriptive User-Agent with real contact info — this
# gets built from NWS_CONTACT_EMAIL and BOARD_TITLE so every deployment
# identifies itself correctly rather than all sharing one string.
_board_title = os.environ.get("BOARD_TITLE", "SitAwareBoard").replace(" ", "")
_nws_contact = os.environ.get("NWS_CONTACT_EMAIL", "admin@example.gov")
NWS_USER_AGENT = f"{_board_title}/1.0 (contact: {_nws_contact})"

_cache = {"periods": None, "fetched_at": None}
CACHE_TTL = timedelta(minutes=20)


def get_forecast():
    """Return a list of NWS forecast periods (3 days = ~6 day/night periods),
    or None if the API call fails. Cached for CACHE_TTL to avoid hammering NOAA."""
    now = datetime.utcnow()
    if _cache["fetched_at"] and now - _cache["fetched_at"] < CACHE_TTL:
        # Respects the cooldown whether the last attempt succeeded or failed —
        # so a NOAA outage doesn't cause every request to retry and block.
        return _cache["periods"]

    try:
        headers = {"User-Agent": NWS_USER_AGENT}
        points_resp = requests.get(
            f"https://api.weather.gov/points/{LAT},{LON}", headers=headers, timeout=6
        )
        points_resp.raise_for_status()
        forecast_url = points_resp.json()["properties"]["forecast"]

        forecast_resp = requests.get(forecast_url, headers=headers, timeout=6)
        forecast_resp.raise_for_status()
        periods = forecast_resp.json()["properties"]["periods"][:6]

        _cache["periods"] = periods
        _cache["fetched_at"] = now
        return periods
    except Exception:
        # Network hiccup, NOAA outage, etc. Still stamp fetched_at so we don't
        # retry (and block a worker for up to ~12s) on every single request
        # during an outage — wait out the same TTL before trying again.
        _cache["fetched_at"] = now
        return _cache["periods"]  # serve stale cache if we have it, else None
