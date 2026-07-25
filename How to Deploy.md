# How to Deploy and Manage

A complete guide for getting this running and keeping it running — written for
whoever ends up as the system administrator, even with no prior Docker background.

## Contents
1. [What you'll need](#1--what-youll-need)
2. [Recommended tools](#2--recommended-tools)
3. [First-time deployment](#3--first-time-deployment)
4. [Understanding what's actually running](#4--understanding-whats-actually-running)
5. [Restarting the application — which command, and when](#5--restarting-the-application--which-command-and-when)
6. [Logs](#6--logs)
7. [Backups](#7--backups)
8. [Updating to a new version](#8--updating-to-a-new-version)
9. [Health and resource monitoring](#9--health-and-resource-monitoring)
10. [Uninstalling / starting over](#10--uninstalling--starting-over)
11. [Troubleshooting](#11--troubleshooting)

---

## 1 — What you'll need
- **A server running Ubuntu Linux** (other distributions work too, but these
  instructions assume Ubuntu). A small cloud VPS or an on-site machine both work fine
  — this application is lightweight. 1–2GB of RAM is plenty.
- **A way to connect to that server.** See the tools below.
- **About 20–30 minutes** for the first deployment.

## 2 — Recommended tools
None of these are required — everything in this guide can be done with just an SSH
terminal — but they make day-to-day administration considerably easier.

**Connecting to the server:**
- **PuTTY** (Windows) — a free SSH terminal. Pairs well with **WinSCP** (Windows) for
  drag-and-drop file transfer to and from the server. This is the combination most
  Windows admins already know.
- **Built-in `ssh`/`scp`** (Mac/Linux, and modern Windows 10/11) — no install needed;
  Terminal already has these.
- **VS Code with the "Remote - SSH" extension** — connects your local VS Code
  directly to the server, giving you a file browser, a text editor, and an integrated
  terminal all in one window. Popular alternative to the PuTTY/WinSCP combo if you're
  already comfortable with VS Code.

**Managing Docker itself, beyond the raw command line:**
- **Plain `docker compose` commands** (covered throughout this guide) — always
  available, nothing extra to install, and the most "official" way to manage this.
  Worth learning even if you also use one of the tools below.
- **lazydocker** — a free, open-source terminal-based dashboard for Docker. Shows
  live container status, logs, and resource usage, and lets you restart/stop
  containers with a keypress, all inside your existing SSH session. No extra service
  to run or secure — it's a single program, not a container. Install with:
  ```
  curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash
  ```
  Then just run `lazydocker` from anywhere.
- **Portainer** (optional, more setup) — a web-based Docker management dashboard.
  More visual and beginner-friendly than a terminal tool, but it runs as its own
  container with its own web login — meaning it's additional attack surface you're
  responsible for securing (its own password, ideally its own access restrictions).
  Reasonable choice if you're managing several Docker projects on the same server and
  want one dashboard for all of them; probably unnecessary if this is the only thing
  running here.

## 3 — First-time deployment

**Install Docker:**
```
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```
Log out and back in for the permission change to take effect, then confirm:
```
docker --version
docker compose version
```

**Get the code onto the server** (WinSCP, `scp`, or `git clone`) into a folder such as
`/opt/sitaware`, then:
```
cd /opt/sitaware
```

**Create your configuration file:**
```
nano .env
```
Minimum required content:
```
SECRET_KEY=<see below>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<pick a real password>
```
Generate the `SECRET_KEY` value with:
```
openssl rand -hex 32
```
Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano). The application will not start
without a real `SECRET_KEY` — this is deliberate, not a bug, and the startup error
tells you exactly how to fix it if you forget this step.

**Build and start it:**
```
docker compose up -d --build
```
First run takes a minute or two.

**Confirm it's running:**
```
docker compose ps
```
Look for `Up`, and `healthy` after about 15 seconds.

**Access it:** `http://your-server-ip:8082` in a browser. Sign in with the admin
credentials from your `.env` to confirm login works.

## 4 — Understanding what's actually running
Everything runs inside a single Docker **container** — an isolated process with its
own filesystem, built from the instructions in the `Dockerfile`. `docker-compose.yml`
describes how to run that container: which port to expose, which environment
variables to pass in, and which folder on the real server (`./data`) maps to a folder
inside the container (`/app/data`) so your database and uploaded files survive even if
the container itself is rebuilt or replaced.

The **image** is the built, reusable template (created by `--build`); the
**container** is a running instance of that image. You rebuild the image after code
changes; you restart or recreate the container to apply configuration changes or pick
up a new image.

## 5 — Restarting the application — which command, and when
This trips people up because the different restart-style commands don't all do the
same thing. Use this table:

| What changed | Command | Why |
|---|---|---|
| Nothing — it's just acting up / you want a clean process restart | `docker compose restart` | Fastest option. Restarts the existing container in place. Does **not** re-read `.env` or pick up code changes. |
| You edited `.env` (passwords, feature toggles, etc.) | `docker compose up -d` | Compose detects the configuration changed and recreates the container with the new values. No rebuild needed if the code itself didn't change. |
| You changed application code, `Dockerfile`, or `requirements.txt` | `docker compose up -d --build` | Rebuilds the image first, then recreates the container from it. This is the command you'll run after almost any update. |
| Nothing is working and you want a fully clean restart | `docker compose down` then `docker compose up -d --build` | Fully stops and removes the container and its network, then rebuilds and recreates from scratch. Your data is untouched (see Backups) — this does not delete `./data`. |

If you're ever unsure which one you need: `docker compose up -d --build` always works
and is safe to run anytime — it's just not always the fastest option.

## 6 — Logs
```
docker compose logs -f
```
Shows live logs; `Ctrl+C` stops watching without stopping the application. Drop the
`-f` to see recent logs without following live:
```
docker compose logs --tail 100
```
Log output is capped at 10MB per file, 5 files, automatically — configured in
`docker-compose.yml` under `logging:` — so logs won't silently consume your entire
disk over months of uptime. You don't need to do anything to maintain this; it's
handled by Docker itself.

## 7 — Backups
The entire application state lives in two things inside the `data/` folder:
`data/briefing.db` (the database) and `data/uploads/` (attachment files). Back these
up like any other files — no special database export tool needed since it's SQLite, a
single file.

A simple daily cron job:
```
0 2 * * * cd /opt/sitaware && tar -czf /backups/sitaware-$(date +\%F).tar.gz data/
```
Store backups somewhere other than this same server — a copy on the same disk
protects against nothing if that disk fails.

## 8 — Updating to a new version
1. Pull or upload the new code (`git pull`, or replace the files via WinSCP)
2. Rebuild and restart:
   ```
   docker compose up -d --build
   ```
Your `.env` file and everything in `data/` are untouched by this — they live outside
the code you're replacing.

## 9 — Health and resource monitoring
```
docker compose ps
```
Shows `healthy`/`unhealthy` status — the container has a built-in healthcheck that
pings the application every 30 seconds. `unhealthy` means the process is running but
not responding correctly; check logs immediately if you see this.

```
docker stats sitaware-briefing
```
Live CPU and memory usage. Useful for confirming this lightweight application is, in
fact, staying lightweight — `Ctrl+C` to exit.

## 10 — Uninstalling / starting over
```
docker compose down
```
Stops and removes the container. **This does not delete your data** — `./data` is a
plain folder on the server (a "bind mount"), not something Docker manages or removes,
so it survives this command regardless of any flags. To actually delete everything
including your data, you'd need to separately `rm -rf data/` — that's a manual,
deliberate step, not something any `docker compose` command does on its own.

## 11 — Troubleshooting

**"docker: command not found"** — Docker didn't finish installing, or you haven't
logged out and back in since installing it (the permission change needs a fresh
session).

**Container immediately exits, or shows "Restarting" in `docker compose ps`** — run
`docker compose logs` and read the last few lines. The most common first-run cause is
a missing or placeholder `SECRET_KEY` in `.env`.

**Can't reach it in the browser** — confirm your server's firewall allows port 8082,
and make sure you're using the server's real IP address rather than `localhost`
(unless you're browsing from the server itself).

**Errors mentioning `/app/data` or "permission denied"** — the `data` folder needs to
be owned by the same user the container runs as (UID 1000):
```
sudo chown -R 1000:1000 data/
docker compose up -d --build
```

**Still stuck** — `docker compose logs` shows the specific error in almost every case;
that's the first place to look before anything else.
