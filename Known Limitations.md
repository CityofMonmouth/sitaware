# Known Limitations

Honest tradeoffs made deliberately for this scale of deployment — not bugs, just
things worth knowing before you rely on this for anything. Everything here is
verified against the current code, not general assumptions.

## Database: SQLite, single-writer
The database is a single SQLite file (`data/briefing.db`). This is fine for the
scale this is built for — a handful of staff posting a few times a day — but SQLite
allows only one write at a time. If this ever needs to support heavy concurrent
posting across many simultaneous users, migrate to PostgreSQL or MariaDB; the
SQLAlchemy layer makes that a one-line config change (`SQLALCHEMY_DATABASE_URI` in
`app/__init__.py`), not a rewrite.

## Rate limiting is approximate, not exact
Login and posting are rate-limited, but the counters are stored in memory, and the
app runs 3 separate gunicorn worker *processes* (`-w 3` in the `Dockerfile`) — each
process has its own counter. The real-world effective limit is roughly 3× what's
configured, since requests are spread across workers. This is still a meaningful
improvement over no limiting at all, but if you need it exact, that requires a shared
store (Redis) instead of in-memory tracking — not implemented, since it's a
meaningful new dependency for a limitation that mostly matters at a scale this
software isn't aimed at.

## Attachments are never automatically deleted
Deleting a post deletes its attachments. Posts that age into the Archive keep their
attachments on disk indefinitely — this is intentional (the point of the Archive is
to preserve history), but it does mean `data/uploads/` will grow over time unless old
material is periodically cleaned out manually.

## Notifications are fire-and-forget, with no delivery confirmation
Email and SMS notifications send in a background thread with no retry queue and no
per-recipient delivery confirmation. If the mail server or Twilio is unreachable at
the moment of sending, that one notification is simply lost, not retried later. The
board itself is always the authoritative source of truth — notifications are a
convenience layer on top of it, not a substitute for someone actually checking the
board during an active incident.

## No malware scanning on uploads
Uploaded files are restricted by extension (PDF, JPG, PNG) and served with
`X-Content-Type-Options: nosniff` to prevent content-sniffing tricks, but there's no
antivirus/malware scanning of file contents. Worth adding if upload access is ever
widened beyond trusted, authenticated staff.

## What's already handled — so it isn't mistaken for a gap
- CSRF protection is applied application-wide, not just on forms that explicitly
  request it.
- A real Content-Security-Policy is set on every response, scoped to exactly the
  external hosts the app uses (Google Fonts, NWS radar/space-weather images) — no
  inline scripts are permitted anywhere in the templates.
- Login is rate-limited and uses a timing-safe comparison to prevent username
  enumeration via response timing.
- Sessions use `HttpOnly`, `SameSite=Lax` cookies with a 12-hour lifetime; the shared
  Agency Access cookie is a completely separate mechanism from personal login
  sessions and can never satisfy a posting/admin route's access check.
- The container runs as a non-root user, not root.
- `SECRET_KEY` is validated at startup — the app refuses to run with a missing or
  placeholder value rather than silently operating insecurely.
