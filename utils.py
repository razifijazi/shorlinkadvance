"""Source detection, user-agent parsing, and A/B variant selection helpers."""
import re
import hashlib
from urllib.parse import urlparse, parse_qs


# Domain -> label map. Order matters: check more specific first.
DOMAIN_LABEL_MAP = [
    (["facebook.com", "fb.com", "fb.me", "m.me", "lm.facebook.com"], "facebook"),
    (["t.co", "twitter.com", "x.com", "mobile.twitter.com"], "twitter"),
    (["pinterest.com", "pin.it", "id.pinterest.com"], "pinterest"),
    (["tiktok.com", "vm.tiktok.com", "m.tiktok.com"], "tiktok"),
    (["instagram.com", "l.instagram.com"], "instagram"),
    (["linkedin.com", "lnkd.in", "lnk.bio"], "linkedin"),
    (["reddit.com", "out.reddit.com", "redd.it"], "reddit"),
    (["youtube.com", "youtu.be", "m.youtube.com"], "youtube"),
    (["whatsapp.com", "wa.me", "web.whatsapp.com"], "whatsapp"),
    (["t.me", "telegram.org", "telegram.me"], "telegram"),
    (["discord.gg", "discord.com", "discordapp.com"], "discord"),
    (["snapchat.com"], "snapchat"),
    (["threads.net", "threads.com"], "threads"),
    (["bsky.app"], "bluesky"),
    (["google.com", "google.co.id", "google.co.uk"], "google"),
    (["bing.com"], "bing"),
    (["duckduckgo.com"], "duckduckgo"),
]


def detect_source(request_args, referer_header, query_param_key=None):
    """Determine traffic source label from inbound request.

    Priority:
    1. utm_source in query
    2. configured query_param (e.g. ?ref=)
    3. referer header domain lookup
    4. 'direct'
    """
    # 1. UTM source
    utm = request_args.get("utm_source")
    if utm:
        return f"utm:{utm}", referer_header

    # 2. Custom ref param
    if query_param_key:
        ref = request_args.get(query_param_key)
        if ref:
            return ref, referer_header

    # 3. Generic 'ref' fallback
    ref = request_args.get("ref")
    if ref:
        return ref, referer_header

    # 4. Parse referer header
    if referer_header:
        try:
            host = urlparse(referer_header).netloc.lower()
            host = re.sub(r"^www\.", "", host)
            for domains, label in DOMAIN_LABEL_MAP:
                for d in domains:
                    if host == d or host.endswith("." + d):
                        return f"ref:{label}", referer_header
            # Unknown referer - use host as label
            return f"ref:{host}", referer_header
        except Exception:
            pass

    return "direct", None


def parse_user_agent(ua):
    """Return (device_type, browser, os) tuple. Best-effort, no external deps."""
    if not ua:
        return ("unknown", "unknown", "unknown")

    ua_lower = ua.lower()

    # Device type
    if "ipad" in ua_lower or "tablet" in ua_lower:
        device = "tablet"
    elif "iphone" in ua_lower or "android" in ua_lower or "mobile" in ua_lower:
        device = "mobile"
    else:
        device = "desktop"

    # Browser
    if "edg/" in ua_lower:
        browser = "Edge"
    elif "firefox/" in ua_lower:
        browser = "Firefox"
    elif "chrome/" in ua_lower or "crios/" in ua_lower:
        browser = "Chrome"
    elif "safari/" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "opera/" in ua_lower or "opr/" in ua_lower:
        browser = "Opera"
    elif "samsungbrowser/" in ua_lower:
        browser = "Samsung"
    else:
        browser = "Other"

    # OS
    if "windows" in ua_lower:
        os_name = "Windows"
    elif "mac os x" in ua_lower or "macintosh" in ua_lower:
        os_name = "macOS"
    elif "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "iOS"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "linux" in ua_lower:
        os_name = "Linux"
    else:
        os_name = "Other"

    return (device, browser, os_name)


def hash_ip(ip):
    """Hash IP for privacy. 24h salt would be better but keeping it simple for P1."""
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def pick_variant(destinations, link_id, ip_hash_str):
    """Sticky weighted random. Same IP+link always gets same variant.

    destinations: list of {url: str, weight: int} or None
    Returns: url string
    """
    if not destinations:
        return None
    total = sum(d.get("weight", 1) for d in destinations)
    if total <= 0:
        return destinations[0]["url"]
    # Stable hash for stickiness
    h = hashlib.sha256(f"{link_id}:{ip_hash_str}".encode()).hexdigest()
    bucket = int(h[:8], 16) % total
    acc = 0
    for d in destinations:
        acc += d.get("weight", 1)
        if bucket < acc:
            return d["url"]
    return destinations[-1]["url"]


def build_destination_url(base_url, link, request_args):
    """Apply strategy (utm / query_param / direct) to base_url.

    Returns the final URL to redirect to.
    """
    strategy = link["strategy"]
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)

    if strategy == "utm":
        if link["utm_source"]:
            qs.setdefault("utm_source", [link["utm_source"]])
        if link["utm_medium"]:
            qs.setdefault("utm_medium", [link["utm_medium"]])
        if link["utm_campaign"]:
            qs.setdefault("utm_campaign", [link["utm_campaign"]])
        if link["utm_content"]:
            qs.setdefault("utm_content", [link["utm_content"]])
        # Inherit inbound utm_* if present (so ?utm_source=tiktok from share link passes through)
        for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
            v = request_args.get(k)
            if v:
                qs[k] = [v]

    elif strategy == "query_param":
        if link["query_param_key"] and link["query_param_value"]:
            # Only set if not already in inbound
            if not request_args.get(link["query_param_key"]):
                qs.setdefault(link["query_param_key"], [link["query_param_value"]])
        # Also pass through any inbound ref
        ref = request_args.get("ref")
        if ref:
            qs["ref"] = [ref]

    # strategy == "direct": no params added

    new_query = "&".join(f"{k}={v[0]}" for k, v in qs.items())
    new_parsed = parsed._replace(query=new_query)
    return new_parsed.geturl()


def generate_random_code(length=6):
    """Random short_code from base32 alphabet, excluding ambiguous chars."""
    import secrets
    alphabet = "23456789abcdefghjkmnpqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(length))
