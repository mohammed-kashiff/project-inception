"""Defanging: makes IOC values safe to display (NFR -- accidental clicks on a
live malicious URL/IP are a real risk in a threat-intel dashboard). Hashes
and CVEs aren't clickable/executable, so they're left as-is.
"""

DEFANGABLE_TYPES = {"ip", "domain", "url"}


def defang(indicator_type: str, value: str) -> str:
    if indicator_type not in DEFANGABLE_TYPES:
        return value

    result = value.replace("http://", "hxxp://").replace("https://", "hxxps://")
    result = result.replace(".", "[.]")
    return result
