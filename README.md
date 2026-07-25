# Situational Awareness Board

A free, self-hosted situational awareness and alerting board built for small and rural
emergency management agencies — the ones priced out of Everbridge, CodeRED, or WebEOC.

Post updates with a priority level, automatically alert staff by email and SMS on
urgent items, and give your agency (or partner agencies) a shared live view of what's
happening — with weather and radar built in.

## Why this exists

This started as an internal tool built by a solo municipal IT administrator for a
small Illinois city and county, covering both the police department and emergency
management. It grew into a full situational awareness platform — and rather than
sell it, the City of Monmouth, Illinois released it as free, open-source software so
other small and rural agencies with the same budget constraints can use it too.

No subscription, no per-agency licensing fee, no vendor lock-in. Run it yourself, on
hardware you already control.

## Features

- **Situational awareness board** — priority-tagged updates (Urgent / Advisory / Info),
  categorized, with file attachments, auto-archiving, and full-text history
- **Emergency Alert button** — one field, one click, immediately posts an Urgent
  update, emails your distribution list, and texts your SMS alert list
- **Email and SMS notifications** — automatic alerts on urgent posts (via any SMTP
  provider and Twilio), with a separate opt-in distribution list for routine updates
- **Kiosk display mode** — a large-font, no-login view built for a wall-mounted TV,
  auto-refreshing, with weather and radar built in
- **Two-tier access** — full staff accounts for posting/admin, plus an optional shared
  read-only password for partner agencies or the public, with no overlap in what each
  can do
- **Live weather and radar** — NOAA forecast, NEXRAD radar loop, and space weather
  conditions, configured for your location
- **Self-hosted, Docker-based** — runs on a single small server or VPS; you own your
  data, nothing goes through a third-party cloud platform
- **Security-hardened** — CSRF protection, rate limiting, security headers, hardened
  session handling — built and audited for public-internet exposure, not just LAN use

## Quick start

```
git clone https://github.com/CityofMonmouth/sitaware.git
cd sitaware
docker compose up -d --build
```

New to Docker, or want the full walkthrough? Start with
**[How to Deploy.md](How%20to%20Deploy.md)** — it assumes no prior Docker experience
and covers first-time setup through everyday container management.

## Documentation

| Doc | What it covers |
|---|---|
| [How to Deploy.md](How%20to%20Deploy.md) | First-time Docker deployment, ongoing management, restarts, logs, backups, updates |
| [Agency Customization.md](Agency%20Customization.md) | Making it yours — accessing the config file, name, logos, location, email/SMS setup, categories |
| [Going Public.md](Going%20Public.md) | Putting this on the internet safely — VPS, reverse proxy, TLS, firewall |
| [Known Limitations.md](Known%20Limitations.md) | Honest tradeoffs worth knowing before you rely on this — SQLite, rate limiting, notification delivery |

## Tech stack

Flask (Python), SQLite, Docker/Docker Compose, gunicorn. No build step, no frontend
framework — server-rendered HTML with vanilla CSS/JS. Deliberately simple: this is
meant to be maintainable by a generalist IT admin, not a dedicated dev team.

## License

Released under the [GNU Affero General Public License v3.0](LICENSE). In short: free
to use, modify, and self-host for any purpose, including commercially — but if you run
a modified version as a hosted service for others, you must release your modified
source code too. This is intentional: it's meant to stop a vendor from taking this,
rebranding it, and reselling it closed-source to the same agencies it's meant to help.

## Contributing

Issues and pull requests are welcome. This is maintained on a volunteer basis by
municipal IT staff, not a commercial team — response times will vary.

## Support

This software is provided as-is, with no warranty and no SLA (see [LICENSE](LICENSE)).
It's self-supported: read the docs above, check existing issues, or open a new one.
