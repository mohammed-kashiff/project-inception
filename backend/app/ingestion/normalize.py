import hashlib
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)
CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
HASH_LENGTHS = {32, 40, 64}  # md5, sha1, sha256


class InvalidIndicator(ValueError):
    pass


def normalize(indicator_type: str, raw_value: str) -> str:
    """Validate + normalize a raw indicator value (FR5/FR6).

    Raises InvalidIndicator with a human-readable reason on malformed input;
    the caller is responsible for routing that to rejected_records rather
    than storing it as valid data.
    """
    value = (raw_value or "").strip()
    if not value:
        raise InvalidIndicator("empty value")

    if indicator_type == "ip":
        return _normalize_ip(value)
    if indicator_type == "domain":
        return _normalize_domain(value)
    if indicator_type == "url":
        return _normalize_url(value)
    if indicator_type == "hash":
        return _normalize_hash(value)
    if indicator_type == "cve":
        return _normalize_cve(value)

    raise InvalidIndicator(f"unknown indicator_type '{indicator_type}'")


def dedup_key(indicator_type: str, normalized_value: str) -> str:
    digest = hashlib.sha256(f"{indicator_type}|{normalized_value}".encode("utf-8")).hexdigest()
    return digest


def _normalize_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise InvalidIndicator(f"invalid IP: {exc}") from exc


def _normalize_domain(value: str) -> str:
    domain = value.lower().rstrip(".")
    if not DOMAIN_RE.match(domain):
        raise InvalidIndicator(f"invalid domain format: '{value}'")
    return domain


def _normalize_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InvalidIndicator(f"invalid URL: '{value}'")

    host = parts.hostname or ""
    port = parts.port
    default_port = {"http": 80, "https": 443}[parts.scheme]
    netloc = host.lower() if port in (None, default_port) else f"{host.lower()}:{port}"

    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))


def _normalize_hash(value: str) -> str:
    h = value.lower()
    if len(h) not in HASH_LENGTHS or not re.fullmatch(r"[0-9a-f]+", h):
        raise InvalidIndicator(f"invalid hash format/length: '{value}'")
    return h


def _normalize_cve(value: str) -> str:
    cve = value.upper()
    if not CVE_RE.match(cve):
        raise InvalidIndicator(f"invalid CVE format: '{value}'")
    return cve
