# Going Public: Infrastructure Guide

Everything outside the application itself needed to safely expose this to the
internet: where to host it, how to put real TLS in front of it, how to lock down the
server it runs on, and how to keep it patched and backed up.

## Before any of the technical work — decide what's actually public
This application ships with two access tiers, not full anonymous access: a personal
Staff account for posting/admin, and an optional shared "Agency Access" read-only
password (see `Agency Customization.md`). There is no fully anonymous public view by
default — every read-only page requires one of the two.

Still worth deciding deliberately, the same way you'd think through public-records
exemption categories: who actually gets the Agency Access password, how it's
distributed and rotated, and whether every category of post is appropriate even for
that broader, less individually-accountable audience once it's reachable from
anywhere rather than just your internal network.

## VPS, or expose your existing internal server?
You could forward ports 80/443 on your existing network's firewall straight to the
server this already runs on. **Don't, if you can avoid it.** If an internet-facing
app is ever compromised — a dependency vulnerability, a misconfiguration, doesn't
matter how — you want the attacker landing in a throwaway rented server with nothing
else on it, not on the same network segment as anything else you run internally. A
cheap VPS buys that separation for the cost of a coffee a month. This is the standard
reasoning behind network segmentation for anything public-facing, and it applies here
directly, especially if the same admin who runs this also manages other, more
sensitive internal systems.

## Sizing
This application is lightweight — Flask, SQLite, a couple of background threads for
notifications. **1 vCPU / 1–2GB RAM / 25GB SSD is genuinely plenty.** Don't oversize
this; a $5–6/month tier handles it comfortably.

## Provider options
| Provider | Entry tier | Notes |
|---|---|---|
| **Hetzner Cloud** | ~$5–6/mo for 2 vCPU / 4GB / 40GB NVMe | Cheapest by a wide margin, excellent hardware. Confirm a US region is available if latency matters to you — historically EU-centric. |
| **DigitalOcean** | $4–6/mo for 1GB | Most common default choice, excellent docs, huge community. Good first choice if this is new territory. |
| **Vultr** | $4–6/mo entry tier | Similar price point to DO, wide range of regions, simple hourly billing. |
| **Linode (Akamai)** | $5/mo Nanode (1GB) | Similar spec/price to DigitalOcean. |

Any of these work fine — pick based on which region is closest to you and which
documentation style you find easiest to follow the first time through.

## Step-by-step

### 1. Provision the VPS
Ubuntu 24.04 LTS, a region close to you, and add your SSH public key during
creation — don't use password authentication for SSH on an internet-facing box.

### 2. Initial server hardening
```
adduser deployuser
usermod -aG sudo deployuser
rsync --archive --chown=deployuser:deployuser ~/.ssh /home/deployuser
sudo nano /etc/ssh/sshd_config
```
Set:
```
PermitRootLogin no
PasswordAuthentication no
```
```
sudo systemctl restart sshd
```
From now on, SSH in as `deployuser`, not root.

### 3. Firewall (ufw)
```
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```
Notably, **do not** open port 8082 to the internet — the reverse proxy (below) is the
only thing that should be internet-reachable; it talks to the app over the internal
Docker network.

### 4. Fail2ban
```
sudo apt install fail2ban -y
sudo systemctl enable --now fail2ban
```
Default config already covers SSH brute-force protection.

### 5. Automatic security updates
```
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### 6. Install Docker
Follow the same steps as `How to Deploy.md`.

### 7. DNS
Point a subdomain (e.g. `alerts.youragency.gov`) at the VPS's public IP via an A
record. This has to happen before requesting a TLS certificate — Let's Encrypt
validates domain ownership over HTTP.

### 8. Deploy the app — bind to localhost only
Same deployment steps as `How to Deploy.md`, with one change: in
`docker-compose.yml`, change the ports line so the app is only reachable from the
proxy running on the same host, not the world:
```yaml
ports:
  - "127.0.0.1:8082:8082"
```

### 9. Reverse proxy + real TLS (Caddy — recommended for simplicity)
Caddy gets automatic HTTPS with zero certificate management — it talks to Let's
Encrypt itself and renews automatically.
```
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy -y
```
Edit `/etc/caddy/Caddyfile`:
```
alerts.youragency.gov {
    reverse_proxy localhost:8082
}
```
```
sudo systemctl reload caddy
```
Visit your domain over `https://` — should show a valid certificate immediately.

**Alternative: nginx + certbot**, if you'd rather use something more traditional:
```
sudo apt install nginx certbot python3-certbot-nginx -y
```
Create an nginx site config proxying to `localhost:8082`, then:
```
sudo certbot --nginx -d alerts.youragency.gov
```
Certbot sets up auto-renewal via a systemd timer automatically.

### 10. Turn on FORCE_HTTPS and BEHIND_PROXY
Once real TLS is confirmed working, add to `.env`:
```
FORCE_HTTPS=true
BEHIND_PROXY=true
```
`BEHIND_PROXY=true` is required here — without it, rate limiting sees the proxy's IP
for every visitor (so all users share one bucket and an attacker isn't meaningfully
limited), and links inside notification emails/texts point at `localhost:8082`
instead of your public domain. Only enable it once a proxy is actually in front of
the app — enabling it otherwise lets anyone spoof `X-Forwarded-For` to bypass rate
limits.
```
docker compose up -d --build
```

### 11. Test end to end
- Visit the public URL, confirm the padlock/valid cert
- Log in, confirm session works
- Try `http://` — should redirect to `https://` automatically
- From another network (phone on cellular data, not your office wifi) confirm the
  site loads — proves it's actually reachable from outside, not just your own LAN

## Ongoing maintenance
- **OS patching:** handled automatically by unattended-upgrades, but Docker and the
  app's own dependencies need periodic manual updates (`apt update && apt upgrade`,
  then `docker compose up -d --build`).
- **Backups:** see `How to Deploy.md` — the entire app state is `data/briefing.db`
  and `data/uploads/`. Back these up off the VPS, not just onto the same disk.
- **Monitoring:** a free external uptime checker (UptimeRobot or similar) hitting the
  public URL every few minutes and alerting on downtime is a low-effort way to catch
  the most important failure mode — the site being down — with almost no setup.

## Summary checklist
- [ ] VPS provisioned, SSH key-only, root login disabled
- [ ] ufw firewall: only SSH/80/443 open
- [ ] fail2ban running
- [ ] unattended-upgrades configured
- [ ] Docker installed
- [ ] DNS A record pointing at the VPS
- [ ] App deployed, port 8082 bound to localhost only
- [ ] Caddy (or nginx+certbot) reverse proxy with valid HTTPS
- [ ] `FORCE_HTTPS=true` and `BEHIND_PROXY=true` set after TLS confirmed working
- [ ] Tested from outside your network
- [ ] Backup routine in place
- [ ] Some form of uptime monitoring in place
- [ ] Deliberately decided who gets Agency Access and what's appropriate to post
