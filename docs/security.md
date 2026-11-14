# Jobre — Security & Compliance Architecture

## 1. Administrative API Authentication

- Every route under `/api/v1/admin/*` enforces `require_admin_auth` (`apps/api/app/dependencies/auth.py`).
- Credentials (`X-Admin-Key` or `Authorization: Bearer <token>`) are verified using `secrets.compare_digest` to prevent timing side-channel attacks.
- Unauthenticated or invalid requests immediately return `401 Unauthorized`.

---

## 2. SSRF (Server-Side Request Forgery) Defense

Because operators or seed imports can submit arbitrary career URLs for discovery, **every outbound URL** passes through `validate_public_url` (`packages/common/security.py`) and redirect-chain re-validation inside `JobreHttpClient`:
- **Allowed Schemes Only:** Strictly `http` and `https` (`file://`, `ftp://`, `gopher://`, `javascript:` are rejected).
- **Blocked Hostnames:** `localhost`, `*.local`, `*.internal`, `metadata.google.internal`, `169.254.169.254`, `100.100.100.200`.
- **Blocked IP Ranges (IPv4 & IPv6 literals + DNS resolution):** Loopback (`127.0.0.0/8`, `::1`), RFC1918 private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local/cloud metadata (`169.254.0.0/16`, `fe80::/10`), multicast, and unspecified addresses.
- **Redirect Re-validation:** Every HTTP `301`/`302`/`303`/`307`/`308` `Location` target is validated against `validate_public_url` **before** following the redirect, preventing open-redirect SSRF pivots.

---

## 3. HTML Sanitization & XSS Prevention

- Raw job descriptions from third-party ATS/job-board feeds are sanitized during normalization via `BeautifulSoup` (`<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>` stripped) followed by strict `bleach.clean` allowlisting (`packages/normalization/engine.py`).
- SQL queries use parameterized SQLAlchemy 2.0 bindings exclusively.

---

## 4. Ethical Crawling & Rate Limiting

- Jobre **never** bypasses authentication walls, login forms, CAPTCHAs, Cloudflare Turnstile, or WAF blocks. Platforms behind anti-bot challenges (e.g., Eightfold AI, Rippling, Wiley Madgex) are transparently recorded with their HTTP 403/202 limitations rather than circumvented.
- Outbound requests identify themselves transparently (`JobreBot/1.0`) and obey per-host token-bucket rate limits (`JobreHttpClient`) plus exponential backoff on `429 Too Many Requests`.
- Public API routes are protected by `SlidingWindowRateLimitMiddleware` (`apps/api/app/middleware/rate_limit.py`).
