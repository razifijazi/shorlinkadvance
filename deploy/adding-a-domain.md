# Adding a subdomain to ShortLink (3 steps)

For each new domain, do these 3 steps. Takes ~10 minutes per domain.

## Step 1: DNS (Cloudflare or registrar)

Add an A record:

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | `<subdomain>` | `<VPS IP>` | **DNS only** (grey cloud) |

Replace `<subdomain>` with the prefix (e.g. `link`, `short`).
Replace `<VPS IP>` with the production VPS IP (e.g. `43.156.83.32`).

**Important**: If using Cloudflare, set proxy to "DNS only" (grey cloud, not orange). Orange proxy will interfere with aaPanel SSL.

Wait for propagation: `dig <subdomain>.<domain> +short` → should return VPS IP.

## Step 2: aaPanel (VPS hosting the domain)

1. Login to aaPanel
2. **Website** → **Add Site**:
   - Domain: `<subdomain>.<domain>` (e.g. `link.digitalthemeplan.my.id`)
   - PHP: **Pure Static** (no PHP)
3. **Settings** → **Reverse Proxy**:
   - Click "Add reverse proxy"
   - Proxy name: `shortlink`
   - Target URL: `http://127.0.0.1:5071`
   - Send Host header: default (passes through)
   - Save
4. **SSL** → **Let's Encrypt**:
   - Select the subdomain
   - Apply
   - Auto-renew should be on

## Step 3: Add in ShortLink dashboard

1. Browse `https://<subdomain>.<domain>/domains`
2. Click "Add Domain"
3. Fill in:
   - Hostname: `<subdomain>.<domain>`
   - Notes: optional
   - ☑️ SSL enabled
4. Save
5. (Optional) Click "Set primary" if this should be the default for new links

## Verify

```bash
# Should return 200
curl -I https://<subdomain>.<domain>/

# Create a test link with this domain
# Click the link, should redirect to destination
```

## Troubleshooting

| Issue | Fix |
|---|---|
| 502 Bad Gateway | ShortLink not running: `sudo systemctl status shortlink-prod` |
| SSL warning in browser | Wait for Let's Encrypt (5-10 min), or re-apply SSL in aaPanel |
| "Link not registered for X" | Add domain in dashboard with correct hostname |
| 404 on subdomain | DNS not propagated yet, or aaPanel vhost not set up |
