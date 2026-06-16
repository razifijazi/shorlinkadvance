"""Database helpers and schema for ShortLink."""
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "shortlink.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    short_code TEXT UNIQUE NOT NULL,
    title TEXT,
    strategy TEXT NOT NULL DEFAULT 'utm',
    default_destination TEXT NOT NULL,
    destinations_json TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    utm_content TEXT,
    query_param_key TEXT,
    query_param_value TEXT,
    expires_at TEXT,
    max_clicks INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    variant_served TEXT,
    source_label TEXT,
    referer_header TEXT,
    user_agent TEXT,
    ip_hash TEXT,
    device_type TEXT,
    browser TEXT,
    os TEXT,
    FOREIGN KEY (link_id) REFERENCES links(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_clicks_link ON clicks(link_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_links_code ON links(short_code);
"""


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)


def get_link_by_id(link_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()


def get_link_by_code(code):
    with get_db() as conn:
        return conn.execute("SELECT * FROM links WHERE short_code = ?", (code,)).fetchone()


def list_links(limit=None, offset=0):
    with get_db() as conn:
        if limit is not None:
            rows = conn.execute("""
                SELECT l.*, COUNT(c.id) as click_count
                FROM links l
                LEFT JOIN clicks c ON c.link_id = l.id
                GROUP BY l.id
                ORDER BY l.created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()
        else:
            rows = conn.execute("""
                SELECT l.*, COUNT(c.id) as click_count
                FROM links l
                LEFT JOIN clicks c ON c.link_id = l.id
                GROUP BY l.id
                ORDER BY l.created_at DESC
            """).fetchall()
        return rows


def count_links():
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM links").fetchone()
        return row["c"] if row else 0


def create_link(data):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO links (
                short_code, title, strategy, default_destination, destinations_json,
                utm_source, utm_medium, utm_campaign, utm_content,
                query_param_key, query_param_value,
                expires_at, max_clicks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["short_code"],
            data.get("title"),
            data["strategy"],
            data["default_destination"],
            json.dumps(data.get("destinations")) if data.get("destinations") else None,
            data.get("utm_source"),
            data.get("utm_medium"),
            data.get("utm_campaign"),
            data.get("utm_content"),
            data.get("query_param_key"),
            data.get("query_param_value"),
            data.get("expires_at"),
            data.get("max_clicks"),
        ))
        return cur.lastrowid


def update_link(link_id, data):
    with get_db() as conn:
        conn.execute("""
            UPDATE links SET
                short_code = ?, title = ?, strategy = ?, default_destination = ?,
                destinations_json = ?,
                utm_source = ?, utm_medium = ?, utm_campaign = ?, utm_content = ?,
                query_param_key = ?, query_param_value = ?,
                expires_at = ?, max_clicks = ?, is_active = ?
            WHERE id = ?
        """, (
            data["short_code"],
            data.get("title"),
            data["strategy"],
            data["default_destination"],
            json.dumps(data.get("destinations")) if data.get("destinations") else None,
            data.get("utm_source"),
            data.get("utm_medium"),
            data.get("utm_campaign"),
            data.get("utm_content"),
            data.get("query_param_key"),
            data.get("query_param_value"),
            data.get("expires_at"),
            data.get("max_clicks"),
            1 if data.get("is_active") else 0,
            link_id,
        ))


def delete_link(link_id):
    with get_db() as conn:
        conn.execute("DELETE FROM links WHERE id = ?", (link_id,))


def log_click(link_id, variant_served, source_label, referer_header,
              user_agent, ip_hash, device_type, browser, os):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO clicks (
                link_id, variant_served, source_label, referer_header,
                user_agent, ip_hash, device_type, browser, os
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (link_id, variant_served, source_label, referer_header,
              user_agent, ip_hash, device_type, browser, os))


def get_clicks(link_id, limit=200):
    with get_db() as conn:
        return conn.execute("""
            SELECT * FROM clicks WHERE link_id = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (link_id, limit)).fetchall()


def get_click_count(link_id):
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM clicks WHERE link_id = ?", (link_id,)).fetchone()
        return row["c"] if row else 0


# --- Analytics aggregate queries ---

def _since_clause(since_iso):
    return (" AND timestamp >= ?", (since_iso,)) if since_iso else ("", ())


def total_clicks(since_iso=None):
    sql, args = _since_clause(since_iso)
    with get_db() as conn:
        row = conn.execute(f"SELECT COUNT(*) as c FROM clicks WHERE 1=1{sql}", args).fetchone()
        return row["c"] if row else 0


def total_clicks_per_link(since_iso=None):
    sql, args = _since_clause(since_iso)
    with get_db() as conn:
        return conn.execute(f"""
            SELECT l.id, l.short_code, l.title, COUNT(c.id) as clicks
            FROM links l
            LEFT JOIN clicks c ON c.link_id = l.id{sql.replace('timestamp', 'c.timestamp')}
            GROUP BY l.id
            ORDER BY clicks DESC, l.created_at DESC
        """, args).fetchall()


def clicks_by_day(link_id, since_iso):
    """Return list of {day, count} for the given link since timestamp."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DATE(timestamp) as day, COUNT(*) as count
            FROM clicks
            WHERE link_id = ? AND timestamp >= ?
            GROUP BY day
            ORDER BY day
        """, (link_id, since_iso)).fetchall()
        return [dict(r) for r in rows]


def clicks_by_group(link_id, group_col, since_iso, limit=20):
    """Generic group-by query: source_label, device_type, browser, os, variant_served."""
    allowed = {"source_label", "device_type", "browser", "os", "variant_served", "referer_header"}
    if group_col not in allowed:
        raise ValueError(f"Invalid group column: {group_col}")
    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT {group_col} as label, COUNT(*) as count
            FROM clicks
            WHERE link_id = ? AND timestamp >= ?
            GROUP BY {group_col}
            ORDER BY count DESC
            LIMIT ?
        """, (link_id, since_iso, limit)).fetchall()
        return [dict(r) for r in rows]
