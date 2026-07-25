from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
CENTRAL = ZoneInfo("America/Chicago")


def to_central_str(dt):
    """Format a naive UTC datetime (as stored in the database) as a Central
    time string, correctly labeled CST or CDT depending on the date —
    America/Chicago handles the daylight-saving switch automatically, so
    this doesn't need separate summer/winter logic."""
    if dt is None:
        return ""
    aware_utc = dt.replace(tzinfo=UTC)
    local = aware_utc.astimezone(CENTRAL)
    return f"{local.strftime('%Y-%m-%d %H:%M')} {local.tzname()}"
