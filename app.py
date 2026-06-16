"""ShortLink — shortlinks with source tracking & A/B routing.

Phase 1 MVP:
- Create / edit / delete / list links
- /r/<code> redirect with strategy (utm | query_param | direct)
- A/B variant routing (sticky by IP)
- Click logging (source, device, browser, OS)
- Raw click log viewer
"""
import json
import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, abort, flash
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
from utils import (
    detect_source,
    parse_user_agent,
    hash_ip,
    pick_variant,
    build_destination_url,
    generate_random_code,
)

app = Flask(__name__)

# Secret key: env var > persistent file > generate new
# (persistent so sessions survive restarts)
_secret_path = Path(__file__).parent / ".secret_key"
if os.environ.get("FLASK_SECRET"):
    app.secret_key = os.environ["FLASK_SECRET"]
elif _secret_path.exists():
    app.secret_key = _secret_path.read_text().strip()
else:
    _new_secret = secrets.token_hex(32)
    _secret_path.write_text(_new_secret)
    os.chmod(_secret_path, 0o600)
    app.secret_key = _new_secret

# Disable all caching so template changes show up immediately
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Debug: only True in dev (no FLASK_ENV=production)
app.config['DEBUG'] = os.environ.get("FLASK_DEBUG", "0") == "1"

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Initialize DB on import
db.init_db()


# --- Date range helpers ---

RANGE_OPTIONS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


def _parse_range():
    """Get date range from query param. Returns (since_iso, label)."""
    r = request.args.get("range", "30d")
    if r not in RANGE_OPTIONS:
        r = "30d"
    delta = RANGE_OPTIONS[r]
    if delta is None:
        return None, r
    since = datetime.now() - delta
    return since.strftime("%Y-%m-%d %H:%M:%S"), r


def _client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


# --- Pages ---

@app.route("/")
def index():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 10
    total = db.count_links()
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page
    links = db.list_links(limit=per_page, offset=offset)
    # Aggregate counters for header
    totals = {
        "24h": db.total_clicks((datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")),
        "7d": db.total_clicks((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")),
        "30d": db.total_clicks((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")),
        "all": db.total_clicks(None),
    }
    return render_template("index.html", links=links, totals=totals,
                           page=page, total_pages=total_pages, total=total, per_page=per_page)


@app.route("/new", methods=["GET", "POST"])
def new_link():
    domains = db.list_domains()
    primary = db.get_primary_domain()
    if request.method == "POST":
        try:
            data = _parse_form()
        except ValueError as e:
            flash(str(e), "error")
            return render_template("new.html", form=request.form, domains=domains)

        # Auto-generate short_code if empty
        if not data["short_code"]:
            for _ in range(10):
                candidate = generate_random_code(6)
                if not db.get_link_by_code(candidate):
                    data["short_code"] = candidate
                    break
            else:
                flash("Failed to generate unique code, try again", "error")
                return render_template("new.html", form=request.form, domains=domains)

        # Check uniqueness
        if db.get_link_by_code(data["short_code"]):
            flash(f"Short code '{data['short_code']}' already exists", "error")
            return render_template("new.html", form=request.form, domains=domains)

        link_id = db.create_link(data)
        flash(f"Created link /r/{data['short_code']}", "success")
        return redirect(url_for("view_clicks", link_id=link_id))

    # Pre-fill domain_id with primary for new link form
    initial_form = {}
    if primary:
        initial_form["domain_id"] = str(primary["id"])
    return render_template("new.html", form=initial_form, domains=domains)


@app.route("/<int:link_id>/edit", methods=["GET", "POST"])
def edit_link(link_id):
    link = db.get_link_by_id(link_id)
    if not link:
        abort(404)
    domains = db.list_domains()

    if request.method == "POST":
        try:
            data = _parse_form()
        except ValueError as e:
            flash(str(e), "error")
            return render_template("new.html", link=link, form=request.form, domains=domains)

        # Check short_code uniqueness if changed
        if data["short_code"] != link["short_code"]:
            if db.get_link_by_code(data["short_code"]):
                flash(f"Short code '{data['short_code']}' already exists", "error")
                return render_template("new.html", link=link, form=request.form, domains=domains)

        db.update_link(link_id, data)
        flash("Link updated", "success")
        return redirect(url_for("index"))

    # Pre-fill form with current values
    form = {
        "short_code": link["short_code"],
        "title": link["title"] or "",
        "strategy": link["strategy"],
        "default_destination": link["default_destination"],
        "destinations": json.loads(link["destinations_json"]) if link["destinations_json"] else "",
        "utm_source": link["utm_source"] or "",
        "utm_medium": link["utm_medium"] or "",
        "utm_campaign": link["utm_campaign"] or "",
        "utm_content": link["utm_content"] or "",
        "query_param_key": link["query_param_key"] or "",
        "query_param_value": link["query_param_value"] or "",
        "expires_at": link["expires_at"] or "",
        "max_clicks": link["max_clicks"] or "",
        "is_active": "1" if link["is_active"] else "",
        "domain_id": str(link["domain_id"]) if link["domain_id"] else "",
    }
    return render_template("new.html", link=link, form=form, domains=domains)


@app.route("/<int:link_id>/delete", methods=["POST"])
def delete_link(link_id):
    db.delete_link(link_id)
    flash("Link deleted", "success")
    return redirect(url_for("index"))


# --- Domain management ---

@app.route("/domains", methods=["GET"])
def domains_page():
    domains = db.list_domains()
    return render_template("domains.html", domains=domains)


@app.route("/domains", methods=["POST"])
def create_domain_route():
    hostname = (request.form.get("hostname") or "").strip().lower()
    notes = (request.form.get("notes") or "").strip() or None
    is_primary = bool(request.form.get("is_primary"))
    ssl_enabled = bool(request.form.get("ssl_enabled"))

    if not hostname:
        flash("Hostname is required", "error")
        return redirect(url_for("domains_page"))
    if db.get_domain_by_hostname(hostname):
        flash(f"Domain '{hostname}' already exists", "error")
        return redirect(url_for("domains_page"))

    domain_id = db.create_domain(hostname, is_primary=is_primary, notes=notes, ssl_enabled=ssl_enabled)
    flash(f"Added domain {hostname}", "success")
    return redirect(url_for("domains_page"))


@app.route("/domains/<int:domain_id>/primary", methods=["POST"])
def set_primary_domain_route(domain_id):
    if not db.get_domain(domain_id):
        flash("Domain not found", "error")
    else:
        db.set_primary_domain(domain_id)
        flash("Primary domain updated", "success")
    return redirect(url_for("domains_page"))


@app.route("/domains/<int:domain_id>/ssl", methods=["POST"])
def toggle_ssl_route(domain_id):
    domain = db.get_domain(domain_id)
    if not domain:
        flash("Domain not found", "error")
    else:
        new_val = not domain["ssl_enabled"]
        db.update_domain(domain_id, ssl_enabled=new_val)
        flash(f"SSL {'enabled' if new_val else 'disabled'} for {domain['hostname']}", "success")
    return redirect(url_for("domains_page"))


@app.route("/domains/<int:domain_id>/delete", methods=["POST"])
def delete_domain_route(domain_id):
    domain = db.get_domain(domain_id)
    if not domain:
        flash("Domain not found", "error")
        return redirect(url_for("domains_page"))
    link_count = db.count_links_for_domain(domain_id)
    if link_count > 0:
        flash(f"Cannot delete: {link_count} link(s) still use this domain. Reassign or delete them first.", "error")
        return redirect(url_for("domains_page"))
    db.delete_domain(domain_id)
    flash(f"Deleted {domain['hostname']}", "success")
    return redirect(url_for("domains_page"))


@app.route("/<int:link_id>/stats")
def view_stats(link_id):
    link = db.get_link_by_id(link_id)
    if not link:
        abort(404)
    active_tab = request.args.get("tab", "charts")
    since_iso, range_label = _parse_range()
    # If "all" passed as None, use a far-past timestamp so the query works
    since_for_groupby = since_iso or "2000-01-01 00:00:00"

    daily = db.clicks_by_day(link_id, since_for_groupby)
    by_source = db.clicks_by_group(link_id, "source_label", since_for_groupby)
    by_device = db.clicks_by_group(link_id, "device_type", since_for_groupby)
    by_browser = db.clicks_by_group(link_id, "browser", since_for_groupby, limit=8)
    by_os = db.clicks_by_group(link_id, "os", since_for_groupby, limit=8)
    by_variant = db.clicks_by_group(link_id, "variant_served", since_for_groupby)
    by_referer = db.clicks_by_group(link_id, "referer_header", since_for_groupby, limit=10)

    # Raw click log (always fetched for tab label count + clicks tab content)
    clicks = db.get_clicks(link_id, limit=500)

    total = sum(d["count"] for d in daily)
    destinations = json.loads(link["destinations_json"]) if link["destinations_json"] else []

    return render_template(
        "stats.html",
        link=link,
        destinations=destinations,
        total=total,
        clicks=clicks,
        range_label=range_label,
        active_tab=active_tab,
        daily=daily,
        by_source=by_source,
        by_device=by_device,
        by_browser=by_browser,
        by_os=by_os,
        by_variant=by_variant,
        by_referer=by_referer,
    )


@app.route("/<int:link_id>/clicks")
def view_clicks(link_id):
    """Redirect to unified stats page with clicks tab."""
    return redirect(url_for("view_stats", link_id=link_id, tab="clicks"))


# --- Redirect handler ---

@app.route("/r/<code>")
def redirect_short(code):
    link = db.get_link_by_code(code)
    if not link:
        abort(404)

    # Active check
    if not link["is_active"]:
        abort(410, "Link disabled")

    # Expiry check
    if link["expires_at"]:
        try:
            expires = datetime.fromisoformat(link["expires_at"])
            if datetime.now() > expires:
                abort(410, "Link expired")
        except ValueError:
            pass

    # Max clicks check
    if link["max_clicks"]:
        if db.get_click_count(link["id"]) >= link["max_clicks"]:
            abort(410, "Link max clicks reached")

    # Domain validation
    domain = None
    if link["domain_id"]:
        domain = db.get_domain(link["domain_id"])
    if not domain or not domain["is_active"]:
        abort(404, "Domain not configured or disabled")

    # Validate request host matches the link's domain
    request_host = request.host.split(":")[0]  # strip port
    force_id = request.args.get("force_domain")
    if request_host != domain["hostname"]:
        # Allow dev override via ?force_domain=<id> matching the link's domain
        if not (force_id and str(domain["id"]) == str(force_id)):
            abort(404, f"Link not registered for {request.host}")

    # Source detection
    referer = request.headers.get("Referer", "")
    source_label, _ = detect_source(request.args, referer, link["query_param_key"])

    # A/B variant selection (sticky by IP)
    ip_str = _client_ip()
    ip_hash_str = hash_ip(ip_str)
    destinations = json.loads(link["destinations_json"]) if link["destinations_json"] else None
    chosen_url = pick_variant(destinations, link["id"], ip_hash_str) or link["default_destination"]

    # Apply strategy
    final_url = build_destination_url(chosen_url, link, request.args)

    # Parse user agent
    ua = request.headers.get("User-Agent", "")
    device, browser, os_name = parse_user_agent(ua)

    # Log click
    db.log_click(
        link_id=link["id"],
        variant_served=chosen_url,
        source_label=source_label,
        referer_header=referer[:500] if referer else None,
        user_agent=ua[:500] if ua else None,
        ip_hash=ip_hash_str,
        device_type=device,
        browser=browser,
        os=os_name,
    )

    return redirect(final_url, code=302)


# --- Helpers ---

def _parse_form():
    """Parse and validate form data. Returns dict ready for db.create/update."""
    data = {}
    data["short_code"] = (request.form.get("short_code") or "").strip().lower()
    data["title"] = (request.form.get("title") or "").strip() or None
    data["strategy"] = request.form.get("strategy", "utm")
    if data["strategy"] not in ("utm", "query_param", "direct", "simple"):
        raise ValueError("Invalid strategy")
    # "simple" with empty UTM fields = treat as direct (no params appended)
    if data["strategy"] == "simple" and not data.get("utm_source"):
        data["strategy"] = "direct"
    data["default_destination"] = (request.form.get("default_destination") or "").strip()
    if not data["default_destination"]:
        raise ValueError("Default destination is required")
    if not (data["default_destination"].startswith("http://") or
            data["default_destination"].startswith("https://")):
        raise ValueError("Destination must start with http:// or https://")

    # UTM fields
    data["utm_source"] = (request.form.get("utm_source") or "").strip() or None
    data["utm_medium"] = (request.form.get("utm_medium") or "").strip() or None
    data["utm_campaign"] = (request.form.get("utm_campaign") or "").strip() or None
    data["utm_content"] = (request.form.get("utm_content") or "").strip() or None

    # Query param fields
    data["query_param_key"] = (request.form.get("query_param_key") or "").strip() or None
    data["query_param_value"] = (request.form.get("query_param_value") or "").strip() or None

    # Optional limits
    expires_at = (request.form.get("expires_at") or "").strip() or None
    if expires_at:
        try:
            datetime.fromisoformat(expires_at)
        except ValueError:
            raise ValueError("expires_at must be ISO format (e.g. 2026-12-31 or 2026-12-31T23:59)")
    data["expires_at"] = expires_at

    max_clicks_raw = (request.form.get("max_clicks") or "").strip()
    data["max_clicks"] = int(max_clicks_raw) if max_clicks_raw else None

    data["is_active"] = bool(request.form.get("is_active"))

    # Domain selection
    domain_id_raw = request.form.get("domain_id", "").strip()
    if domain_id_raw:
        try:
            domain_id = int(domain_id_raw)
            domain = db.get_domain(domain_id)
            if not domain:
                raise ValueError(f"Domain id {domain_id} not found")
            if not domain["is_active"]:
                raise ValueError(f"Domain {domain['hostname']} is disabled")
            data["domain_id"] = domain_id
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError("Invalid domain selection")
            raise
    else:
        # No domain selected - fall back to primary
        primary = db.get_primary_domain()
        if not primary:
            raise ValueError("No domain selected and no primary domain configured. Add a domain in /domains first.")
        data["domain_id"] = primary["id"]

    # Destinations (A/B variants) - parse from JSON textarea
    dest_raw = (request.form.get("destinations") or "").strip()
    data["destinations"] = None
    if dest_raw:
        try:
            parsed = json.loads(dest_raw)
            if not isinstance(parsed, list):
                raise ValueError("destinations must be a JSON array")
            cleaned = []
            for item in parsed:
                if not isinstance(item, dict) or "url" not in item:
                    raise ValueError("Each destination must have a 'url' field")
                weight = int(item.get("weight", 1))
                if weight < 0:
                    raise ValueError("weight must be >= 0")
                url = item["url"].strip()
                if not (url.startswith("http://") or url.startswith("https://")):
                    raise ValueError(f"Destination URL must start with http(s)://: {url}")
                cleaned.append({"url": url, "weight": weight})
            if not cleaned:
                raise ValueError("destinations array is empty")
            data["destinations"] = cleaned
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid destinations JSON: {e}")

    return data


# --- Error handlers ---

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Link not found"), 404


@app.errorhandler(410)
def gone(e):
    return render_template("error.html", code=410, message=str(e.description)), 410


if __name__ == "__main__":
    debug = app.config.get("DEBUG", False)
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "5071"))
    app.run(host=host, port=port, debug=debug)
