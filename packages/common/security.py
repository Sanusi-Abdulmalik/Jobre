from __future__ import annotations

import hashlib
import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_QUERY_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gh_src",
        "lever-source",
        "lever-origin",
        "ashby_jid",
        "ref",
        "source",
        "src",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "gsessionid",
    }
)

BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
        "100.100.100.200",
    }
)


class SSRFSafetyError(ValueError):
    """Raised when a URL violates SSRF, scheme, or private-network policies."""


def sha256_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _is_forbidden_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(
    url: str,
    *,
    allow_private: bool = False,
    resolve_dns: bool = True,
) -> str:
    """Validate URL scheme, hostname, and resolved IP addresses against SSRF."""
    if not url or not isinstance(url, str):
        raise SSRFSafetyError("URL must be a non-empty string.")
    cleaned = url.strip()
    if len(cleaned) > 2048:
        raise SSRFSafetyError("URL exceeds maximum length of 2048 characters.")

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSafetyError(f"Unsupported URL scheme '{parsed.scheme}'; only http/https allowed.")
    if not parsed.hostname:
        raise SSRFSafetyError("URL must include a valid hostname.")
    if parsed.username or parsed.password:
        raise SSRFSafetyError("Credentials embedded in URLs are forbidden.")

    host = parsed.hostname.lower().rstrip(".")
    if not allow_private:
        if host in BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
            raise SSRFSafetyError(f"Access to internal hostname '{host}' is blocked.")

        # Direct IP literal check
        is_ip_literal = False
        try:
            ipaddress.ip_address(host)
            is_ip_literal = True
        except ValueError:
            is_ip_literal = False

        if is_ip_literal:
            if _is_forbidden_ip(host):
                raise SSRFSafetyError(f"Access to non-public IP '{host}' is blocked.")
        elif resolve_dns:
            try:
                addr_infos = socket.getaddrinfo(
                    host,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    proto=socket.IPPROTO_TCP,
                )
            except socket.gaierror as exc:
                raise SSRFSafetyError(f"DNS resolution failed for '{host}': {exc}") from exc
            for info in addr_infos:
                ip_str = info[4][0]
                if _is_forbidden_ip(ip_str):
                    raise SSRFSafetyError(
                        f"Hostname '{host}' resolved to restricted IP '{ip_str}'."
                    )

    return cleaned


def canonicalize_url(url: str | None) -> str | None:
    """Normalize a URL for deterministic deduplication and storage."""
    if not url:
        return None
    raw = url.strip()
    # HandleJazzHR style &gsessionid appended without ?
    if "&gsessionid=" in raw and "?" not in raw:
        raw = raw.split("&gsessionid=", 1)[0]
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    filtered_qs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_QUERY_PARAMS
    ]
    filtered_qs.sort()
    query = urlencode(filtered_qs)
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_canonical_domain(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host
