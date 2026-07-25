# Agency Customization

Everything in this codebase ships generic on purpose — no specific agency's name,
logos, location, or contact info baked in. This is the complete list of what to
change to make it yours, including full setup walkthroughs for email and SMS alerts.

Every setting below is a `.env` change plus `docker compose up -d --build`, unless a
section explicitly says otherwise.

## Contents
1. [Accessing the configuration file](#1--accessing-the-configuration-file)
2. [Core identity](#2--core-identity)
3. [Logos](#3--logos)
4. [Weather location](#4--weather-location)
5. [Email notifications (SMTP)](#5--email-notifications-smtp)
6. [SMS text alerts (Twilio)](#6--sms-text-alerts-twilio)
7. [Shared read-only access](#7--shared-read-only-access)
8. [Categories and priorities (code edit)](#8--categories-and-priorities-code-edit)
9. [Full settings reference](#9--full-settings-reference)

---

## 1 — Accessing the configuration file
Every setting in this guide lives in one file called `.env`, in the same folder as
`docker-compose.yml` (e.g. `/opt/sitaware/.env`, if that's where you deployed). This
file is never part of the project's source code — you create it yourself, since it
holds real secrets specific to your deployment. If it doesn't exist yet, creating it
is part of the normal first-deploy process, not an error.

**Option A — Terminal (SSH), works on any platform**

Connect to your server:
- **Windows:** PuTTY, or the `ssh` command built into modern Windows Terminal
- **Mac/Linux:** the `ssh` command built into Terminal
```
ssh youruser@your-server-ip
```
Then open the file in a text editor:
```
cd /opt/sitaware
nano .env
```
Make your changes, then save and exit: `Ctrl+O`, `Enter`, `Ctrl+X`. If `.env` doesn't
exist yet, `nano .env` creates it — nothing extra needed.

**Option B — WinSCP (Windows, graphical, no terminal typing required)**

1. Open WinSCP and connect to your server (same login you'd use for SSH)
2. Navigate to your project folder (e.g. `/opt/sitaware`)
3. If `.env` doesn't exist yet: right-click in the file list → **New → File**, and
   name it exactly `.env`
4. Double-click `.env` to open it in WinSCP's built-in text editor
5. Make your changes, then save (`Ctrl+S` or the Save toolbar button) — WinSCP
   uploads the change to the server automatically

WinSCP is often the more comfortable option if a terminal text editor feels
unfamiliar — it behaves like an ordinary text editor window, no keyboard shortcuts
required to save and exit.

**After editing `.env`, apply the change:**
```
docker compose up -d --build
```
Editing the file by itself doesn't change anything until the application is told to
pick up the new values. See the restart command table in `How to Deploy.md` for when
a full rebuild is needed versus a lighter restart.

## 2 — Core identity
```
SECRET_KEY=<run: openssl rand -hex 32>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<a real password>
BOARD_TITLE=Your Agency Situational Awareness Board
FOOTER_CREDIT=Maintained by Your Name — Your Agency
```
`SECRET_KEY` is not optional — the app refuses to start without a real one.
`ADMIN_USERNAME`/`ADMIN_PASSWORD` only take effect on the very first run (when the
user database is empty); changing them later doesn't retroactively change the
existing admin account — use the Users admin page for that instead.
`FOOTER_CREDIT` can be left blank for no credit line at all.

## 3 — Logos
Three generic icons ship by default — a police badge, a fire badge, and an EMS/medical
symbol — at:
```
app/static/logos/default-police.png
app/static/logos/default-fire.png
app/static/logos/default-ems.png
```
displayed as two icons flanking the title on the left, one on the right.

**To use your own logos:** overwrite those three files with your own artwork, keeping
the exact same filenames — no template or code changes needed. Square-ish PNGs with
transparent backgrounds look best (they render inside a white circular badge via CSS).

**To run with no logos at all:**
```
SHOW_LOGOS=false
```

**To change the count or left/right split** (e.g. four logos instead of three): edit
`app/templates/base.html` and `app/templates/kiosk.html` — look for the
`logo-strip-left` / `logo-strip-right` `<div>` blocks and add or remove `<img>` tags.

## 4 — Weather location
```
WEATHER_LOCATION_NAME=Your City, ST
WEATHER_LAT=40.1234
WEATHER_LON=-90.5678
RADAR_STATION_ID=KXXX
NWS_CONTACT_EMAIL=you@youragency.gov
```
- `WEATHER_LAT`/`WEATHER_LON`: your actual coordinates — [latlong.net](https://www.latlong.net)
  or similar will give you these from an address.
- `RADAR_STATION_ID`: your nearest NEXRAD radar site. NOAA's radar station map at
  radar.weather.gov shows every site; pick whichever covers your area.
- `NWS_CONTACT_EMAIL`: required by NOAA's API usage policy — a real, monitored
  address. Generic or placeholder values can get throttled or blocked by NOAA.

## 5 — Email notifications (SMTP)
Until this is configured, the Email List can still be built and posts can still be
flagged for email — nothing actually sends until real SMTP credentials are set. This
is intentional: an unconfigured mail feature fails silently rather than breaking
anything else.

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=you@youragency.gov
SMTP_PASSWORD=your-password-or-app-password
SMTP_FROM_ADDRESS=you@youragency.gov
SMTP_USE_TLS=true
```
**`SMTP_FROM_ADDRESS` generally needs to match `SMTP_USERNAME`** (or be a configured
send-as alias on that account) — most providers reject the send otherwise with an
error like "sender not allowed to relay."

### Provider-specific setup

**Zoho Mail** — `smtp.zoho.com`, port `587`, STARTTLS.
If two-factor authentication is enabled on the account (recommended): go to
accounts.zoho.com → **Security → App Passwords** → **Generate New Password**, and use
that generated value as `SMTP_PASSWORD` instead of the account's real password. If
2FA isn't enabled, the regular account password works directly, though enabling 2FA
plus an app password is the safer long-term setup — it's a credential you can revoke
individually without touching the account's main login.

**Gmail / Google Workspace** — `smtp.gmail.com`, port `587`, STARTTLS.
Google requires an **App Password** for SMTP regardless of 2FA status on newer
accounts — go to myaccount.google.com → **Security → 2-Step Verification → App
passwords**, generate one, and use it as `SMTP_PASSWORD`. 2-Step Verification must be
turned on for the App Passwords option to appear.

**Microsoft 365 / Outlook — currently unreliable, read before using.**
Microsoft has been actively phasing out plain username/password authentication
(including App Passwords) for SMTP in Exchange Online throughout 2026, in favor of
OAuth 2.0. Depending on your tenant's settings, direct SMTP with `SMTP_USERNAME`/
`SMTP_PASSWORD` may already be blocked, or may stop working with no warning even if
it's working today. This application only supports username/password SMTP
authentication, not OAuth — so Microsoft 365 is not a dependable choice right now
without a workaround. If your agency is on Microsoft 365:
- Check with whoever administers your tenant whether "SMTP AUTH" is still enabled for
  your mailbox — it may already be disabled by default.
- If it's not available or not reliable, use a dedicated transactional email service
  instead (see below) rather than fighting Microsoft's deprecation timeline.

**Dedicated transactional email services** (recommended if Zoho/Gmail aren't options,
or if Microsoft 365 SMTP isn't working) — Mailgun, SendGrid, Amazon SES, and Postmark
are all purpose-built for exactly this kind of application-sends-email use case, all
support standard SMTP username/password authentication (typically an API key used as
the password), and all have free tiers well beyond what a single agency's alert
volume would ever need. Sign up, verify your sending domain per their instructions,
and use the SMTP credentials they issue.

## 6 — SMS text alerts (Twilio)
Same pattern as email: until configured, texts are silently skipped rather than
failing loudly.

**Why Twilio, not a free carrier gateway:** the old approach of emailing
`number@vtext.com`-style carrier addresses is no longer dependable — major carriers
have discontinued or degraded these gateways. Twilio costs a small amount of money
but actually works.

**One-time setup:**
1. Create a Twilio account at twilio.com and add billing (pay-as-you-go, no monthly
   minimum at this scale).
2. Buy a phone number (Console → Phone Numbers → Buy a Number) — any US local or
   toll-free number works, roughly $1–2/month.
3. **Register for A2P 10DLC** (Console → Messaging → Regulatory Compliance) — US
   carriers now require this brand/campaign registration for application-to-person
   SMS traffic sent from a standard number. It's a one-time process that can take
   anywhere from same-day to a few business days to clear. Messages sent before this
   clears may be filtered or blocked by carriers. Government/municipal senders
   sometimes qualify for simpler verification — worth asking Twilio support directly.
4. From the Console dashboard, copy your **Account SID** and **Auth Token**.

**Add to `.env`:**
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_FROM_NUMBER=+15551234567
```

**Cost reality check:** for a small distribution list with texts only firing on
Urgent-priority posts, this realistically runs a few dollars a month total
(~$0.008–0.01 per text plus the number rental) — not a meaningful budget line.

## 7 — Shared read-only access
```
AGENCY_PASSWORD=some-shared-passphrase
```
A single password (not tied to any named account) that grants read-only viewing —
the board, archive, weather, and kiosk — without posting or admin access. Useful for
partner agencies, mutual aid contacts, or the public, without creating individual
accounts for each. Leave unset to disable this login path entirely.

## 8 — Categories and priorities (code edit)
Update categories and priority levels live in `app/forms.py`:
```python
CATEGORY_CHOICES = [
    ("incident", "Incident"),
    ("weather_road", "Weather / Road Conditions"),
    ...
]
PRIORITY_CHOICES = [
    ("urgent", "Urgent"),
    ("advisory", "Advisory"),
    ("info", "Info"),
]
```
The value on the left (e.g. `"incident"`) is what's stored in the database; the label
on the right is what displays. Add or rename freely going forward, but **don't remove
or change the value (left side) of a category that's already been used** — existing
posts would show the raw stored value instead of a label until either the old choice
stays in the list or the existing rows are migrated.

Priority levels are more deeply wired into the app than categories — `"urgent"`
specifically triggers SMS alerts and the board's urgent banner. Adding a 4th priority
level touches more code than adding a category; only worth doing if you're
comfortable reading through `app/routes.py`'s priority-handling logic first.

## 9 — Full settings reference

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | *(required, no default)* | Signs sessions and Agency Access tokens. App refuses to start without a real value. |
| `ADMIN_USERNAME` | `admin` | First-run admin account username only |
| `ADMIN_PASSWORD` | `ChangeMe123!` | First-run admin account password only — change immediately |
| `BOARD_TITLE` | `Situational Awareness Board` | Site title, shown in header and browser tab |
| `FOOTER_CREDIT` | *(blank)* | Optional footer credit line |
| `SHOW_LOGOS` | `true` | Show/hide the header logo strip |
| `WEATHER_LOCATION_NAME` | `your area` | Display label on weather panels |
| `WEATHER_LAT` / `WEATHER_LON` | Placeholder coordinates | Location used for the NWS forecast |
| `RADAR_STATION_ID` | `KDVN` | NEXRAD radar site code |
| `NWS_CONTACT_EMAIL` | `admin@example.gov` | Required contact info for NOAA's API |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_ADDRESS` / `SMTP_USE_TLS` | All blank except port `587` and TLS `true` | Email notifications — blank host disables sending |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | All blank | SMS alerts — blank disables sending |
| `AGENCY_PASSWORD` | *(blank)* | Shared read-only login — blank disables this login path |
| `FORCE_HTTPS` | `false` | Only set `true` once a real TLS certificate is in front of the app via reverse proxy |
| `BEHIND_PROXY` | `false` | Only set `true` when actually running behind a reverse proxy — fixes rate limiting and notification links |

`FORCE_HTTPS` and `BEHIND_PROXY` only apply to an internet-facing deployment behind a
reverse proxy with a real certificate — leave both `false` for a plain internal LAN
deployment.
