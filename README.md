# ShortLink

Self-hosted shortlink service with source tracking & A/B routing.

## Features

- **Shortlinks** with auto-generated or custom short codes
- **Strategy options**:
  - **UTM** (manual) — append `utm_source/medium/campaign/content`
  - **Simple** (preset) — pick from 17 common sources (Facebook, Instagram, TikTok, etc.)
  - **Query param** — append custom `?ref=fb` style param
  - **Direct** — no params
- **A/B variant routing** — sticky by IP, weighted distribution
- **Source detection** — auto-detect Facebook/Twitter/Instagram/etc. from referer header
- **Click tracking** — source, device, browser, OS, country (planned)
- **Analytics dashboard** — line/doughnut/bar charts via Chart.js
- **Tabbed stats view** — Charts + Raw Clicks in one page
- **Pagination** — 10 links per page
- **Copy shortlink** button with clipboard fallback
- **Date range filter** — 24h / 7d / 30d / all-time
- **Link limits** — expiry date, max clicks

## Quick Start

```bash
# Clone
git clone git@github.com:razifijazi/shorlinkadvance.git
cd shorlinkadvance

# Setup venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
python app.py
# → http://localhost:5071
```

## Configuration

All settings live in `app.py` and `db.py` — no env vars needed for basic operation.

To change port, edit the bottom of `app.py`:
```python
app.run(host="0.0.0.0", port=5071, debug=True)
```

## Database

Uses SQLite (`shortlink.db`, auto-created on first run). No external DB needed.

Schema:
- `links` — short_code, strategy, destinations, UTM defaults
- `clicks` — source, device, browser, OS, ip_hash, timestamp

## Project Structure

```
shorlinkadvance/
├── app.py              # Flask routes
├── db.py               # SQLite helpers + schema
├── utils.py            # Source detection, UA parsing, A/B pick
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── index.html      # Link list + pagination
│   ├── new.html        # Create/edit form (with Simple mode)
│   ├── stats.html      # Charts + Raw Clicks (tabbed)
│   └── error.html
└── static/
```

## Production Deployment

Use gunicorn or systemd. Example systemd unit:

```ini
[Unit]
Description=ShortLink Flask App
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/shortlink
ExecStart=/home/ubuntu/shortlink/.venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Or with gunicorn:
```bash
.venv/bin/pip install gunicorn
.venv/bin/gunicorn -w 2 -b 0.0.0.0:5071 app:app
```

## Roadmap

- [ ] Country geolocation (IP → country)
- [ ] QR code generation per link
- [ ] Password-protected links
- [ ] CSV export of click log
- [ ] Bulk create from CSV
- [ ] Custom domain (e.g. `link.digitalthemeplan.my.id`)

## License

MIT
