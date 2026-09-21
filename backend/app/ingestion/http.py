import time

import requests

MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2


def request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """HTTP request with exponential backoff on network errors, 429s, and 5xx.

    A source being unavailable or rate-limited (FR4) should not crash the
    whole ingestion run -- callers still need to catch exceptions from this
    for the case where all attempts are exhausted.
    """
    kwargs.setdefault("timeout", 30)
    last_exc: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"{response.status_code} from {url}", response=response)
            response.raise_for_status()
            return response
        except (requests.RequestException,) as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_BASE_SECONDS ** attempt)

    raise last_exc
