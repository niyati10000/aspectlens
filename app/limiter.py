"""Rate limiter configuration and client IP resolution for AspectLens."""

from slowapi import Limiter
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Extract client IP address, properly respecting X-Forwarded-For behind reverse proxies (e.g. Hugging Face Spaces)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


limiter = Limiter(key_func=get_client_ip, default_limits=[])
