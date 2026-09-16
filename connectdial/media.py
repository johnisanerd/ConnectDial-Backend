"""SportTribe media URL helpers.

Firebase/Google Cloud Storage is the permanent media store.  Clients receive
short-lived signed HTTPS URLs and never see internal Docker hostnames.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import urlparse

from .firebase_storage import signed_media_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ByteRange:
    """Kept for compatibility with regression tests and legacy helpers."""

    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_byte_range(header: str | None, size: int) -> Optional[ByteRange]:
    """Parse a single RFC 7233 byte range.

    Firebase/GCS handles byte ranges directly for signed URLs, but this helper
    remains useful for tests and any legacy callers.
    """
    if not header:
        return None
    if size <= 0:
        raise ValueError("empty object")

    value = header.strip()
    if not value.lower().startswith("bytes="):
        raise ValueError("unsupported range unit")

    spec = value[6:].strip()
    if not spec or "," in spec or "-" not in spec:
        raise ValueError("invalid byte range")

    start_text, end_text = spec.split("-", 1)
    if not start_text:
        if not end_text.isdigit():
            raise ValueError("invalid suffix range")
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("invalid suffix length")
        suffix = min(suffix, size)
        return ByteRange(size - suffix, size - 1)

    if not start_text.isdigit():
        raise ValueError("invalid range start")
    start = int(start_text)
    if start >= size:
        raise ValueError("range start beyond object")

    if end_text:
        if not end_text.isdigit():
            raise ValueError("invalid range end")
        end = int(end_text)
        if end < start:
            raise ValueError("range end before start")
        end = min(end, size - 1)
    else:
        end = size - 1

    return ByteRange(start, end)


def _clean_key(name: str) -> str:
    raw = (name or "").strip().lstrip("/")
    path = PurePosixPath(raw)
    if not raw or ".." in path.parts:
        raise ValueError("invalid media key")
    return str(path)


def build_media_url(file_field_or_name, request=None) -> Optional[str]:
    """Return an absolute external URL or a signed Firebase/GCS URL.

    ``request`` is accepted for backwards compatibility with serializer calls.
    """
    if not file_field_or_name:
        return None

    name = getattr(file_field_or_name, "name", file_field_or_name)
    if not name:
        return None

    value = str(name).strip()
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value

    try:
        key = _clean_key(value)
        return signed_media_url(key)
    except Exception as exc:
        logger.warning("Could not generate signed media URL for %r: %s", value, exc)
        return None


def storage_object_response(request, key: str, *, head_only: bool = False):
    """Legacy compatibility response: redirect storage reads to Firebase/GCS."""
    from django.http import HttpResponse, HttpResponseRedirect

    try:
        key = _clean_key(key)
        url = signed_media_url(key)
    except Exception:
        return HttpResponse(status=404)

    # GCS handles GET/HEAD, Range requests, seek and caching after redirect.
    return HttpResponseRedirect(url)
