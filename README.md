# ShortLink

Self-hosted shortlink service with source tracking, A/B routing, and multi-domain support.

## Features

- **Shortlinks** with auto-generated or custom short codes
- **Multi-domain support** — run multiple custom domains, each with its own shortlinks
- **Strategy options**:
  - **UTM** (manual) — append `utm_source/medium/campaign/content`
  - **Simple** (preset) — pick from 17 common sources (Facebook, Instagram, TikTok, etc.)
  - **Query param** — append custom `?ref=fb` style param
  - **Direct** — no params
- **A/B variant routing** — sticky by IP, weighted distribution
- **Source detection** — auto-detect Facebook/Twitter/Instagram/etc. from referer header
- **Click tracking** — source, device, browser, OS, variant, timestamp
- **Analytics dashboard** — line/doughnut/bar charts via Chart.js
- **Tabbed stats view** — Charts + Raw Clicks in one page
- **Pagination** — 10 links per page
- **Copy shortlink** button uses the link's bound domain (not current URL)
- **Date range filter** — 24h / 7d / 30d / all-time
- **Link limits** — expiry date, max clicks
- **Per-domain validation** — shortlinks only work on their bound domain

## Quick Start (Local Dev)

```bash
# Clone
git clone git@github.com:razifijazi/shorlinkadvance.git
cd shorlinkadvance

# Setup venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run (dev mode, debug=True)
python app.py
# → http://localhost:5071
```

## Two-Environment Setup (Recommended)

This project supports separate dev and production environments with isolated databases:

```
LOCAL DEV (your machine or test VPS)         PRODUCTION (live VPS)
  /home/ubuntu/shortlink/                      /home/ubuntu/shortlink-prod/
  shortlink.db (test data)                     shortlink-prod.db (live data)
  python app.py                                gunicorn + systemd
       │                                              ▲
       │ git push                                     │ git pull
       ▼                                              │
       GitHub (shorlinkadvance) ──────────────────────┘
```

### Why two environments?

- Dev can be broken freely without affecting live shortlinks
- Test data never leaks to production
- Production runs on the same VPS that hosts the public domain
- Independent failure domains

## Adding a Custom Domain

See [`deploy/adding-a-domain.md`](deploy/adding-a-domain.md) for full instructions.

Quick summary (3 steps):
1. **DNS**: A record for subdomain → VPS IP
2. **aaPanel**: Add site + reverse proxy to `http://127.0.0.1:5071` + Let's Encrypt SSL
3. **Dashboard**: Add hostname at `/domains` page, set as primary if desired

## Production Deployment

```bash
# On production VPS, first time:
cd /home/ubuntu
git clone git@github.com:razifijazi/shorlinkadvance.git shortlink-prod
cd shortlink-prod
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run deploy script (installs systemd service, restarts, etc.)
bash deploy/deploy-prod.sh
```

The deploy script:
- Pulls latest from GitHub
- Updates Python deps
- Initializes/updates DB (idempotent)
- Installs systemd service (first run only)
- Restarts the service
- Verifies the service is healthy

### Manual service commands

```bash
sudo systemctl status shortlink-prod    # check status
sudo systemctl restart shortlink-prod    # restart
sudo systemctl stop shortlink-prod       # stop
sudo journalctl -u shortlink-prod -f    # follow logs
```

## Configuration

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SHORTLINK_DB` | `<app dir>/shortlink.db` | Path to SQLite database file |
| `FLASK_SECRET` | (auto-generated, stored in `.secret_key`) | Flask session secret |
| `FLASK_DEBUG` | `0` | Set to `1` for dev mode (debug pages, auto-reload) |
| `FLASK_HOST` | `0.0.0.0` | Bind address |
| `FLASK_PORT` | `5071` | Bind port |

### Production systemd

See [`deploy/shortlink-prod.service`](deploy/shortlink-prod.service). Default config:
- 2 gunicorn workers
- Bind to `127.0.0.1:5071` (only accessible via reverse proxy)
- Logs to `access.log` / `error.log` in app dir
- Auto-restart on crash
- Hardening: no new privileges, private /tmp, read-only home

## Database

Uses SQLite. Path configurable via `SHORTLINK_DB` env var (default: next to `app.py`).

Schema:
- `domains` — hostname, is_primary, is_active, ssl_enabled, notes
- `links` — short_code, strategy, destinations, UTM defaults, domain_id (FK)
- `clicks` — source, device, browser, OS, ip_hash, timestamp, variant_served

Migration: `db.init_db()` is idempotent. Run on every deploy to handle schema upgrades.

## Project Structure

```
shorlinkadvance/
├── app.py              # Flask routes
├── db.py               # SQLite helpers + schema
├── utils.py            # Source detection, UA parsing, A/B pick
├── wsgi.py             # Gunicorn entrypoint
├── requirements.txt
├── .gitignore
├── README.md
├── deploy/
│   ├── deploy-prod.sh          # Production deploy script
│   ├── shortlink-prod.service  # systemd unit file
│   └── adding-a-domain.md      # DNS + aaPanel guide
├── templates/
│   ├── base.html
│   ├── index.html      # Link list + pagination
│   ├── new.html        # Create/edit form (with Simple mode, domain dropdown)
│   ├── stats.html      # Charts + Raw Clicks (tabbed)
│   ├── domains.html    # Domain management
│   └── error.html
└── static/
```

## Development Notes

- **No auth yet** — single-user, URL = full admin access. For multi-user, add login (planned V2).
- **Test override** — when testing locally, append `?force_domain=<id>` to bypass Host check.
- **A/B sticky by IP** — same visitor always gets same variant until you change weights.

## Roadmap

- [ ] Country geolocation (IP → country)
- [ ] QR code generation per link
- [ ] Password-protected links
- [ ] CSV export of click log
- [ ] Bulk create from CSV
- [ ] Basic auth / login
- [ ] API for programmatic link creation
- [ ] Daily DB backup automation
- [ ] DNS auto-check (warn if hostname doesn't resolve to VPS)

## License

MIT

