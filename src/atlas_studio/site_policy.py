from urllib.parse import urlsplit


def validate_site_url(value: str, allowed_origins: set[str]) -> str:
    candidate = value.strip() or "http://app:8080/"
    parsed = urlsplit(candidate)
    if parsed.username or parsed.password or parsed.scheme not in {"http", "https"}:
        raise ValueError("site inspection requires an allow-listed HTTP URL")
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if origin not in allowed_origins:
        raise ValueError("site inspection is limited to configured Atlas Studio origins")
    return candidate
