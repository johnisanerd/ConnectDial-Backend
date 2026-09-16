"""Public media URL helpers and S3/MinIO streaming primitives.

The app stores objects in an internal MinIO endpoint (``http://minio:9000``),
which must never be exposed to mobile clients. Public clients use the existing
HTTPS API domain and this module proxies object reads, including HTTP byte-range
requests used by native video players.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Optional
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse

CHUNK_SIZE = 512 * 1024


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_byte_range(header: str | None, size: int) -> Optional[ByteRange]:
    """Parse a single RFC 7233 ``Range`` header.

    Returns ``None`` when no range was supplied and raises ``ValueError`` for
    malformed/unsatisfiable ranges. Multiple ranges are intentionally rejected
    because mobile players only require a single contiguous range.
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
        # Suffix range: bytes=-500
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
    raw = (name or "").lstrip("/")
    path = PurePosixPath(raw)
    if not raw or ".." in path.parts:
        raise ValueError("invalid media key")
    return str(path)


def build_media_url(file_field_or_name, request=None) -> Optional[str]:
    """Build a public HTTPS URL without leaking the internal MinIO hostname."""
    if not file_field_or_name:
        return None

    name = getattr(file_field_or_name, "name", file_field_or_name)
    if not name:
        return None

    try:
        key = _clean_key(str(name))
    except ValueError:
        return None

    base = getattr(settings, "PUBLIC_API_BASE_URL", "https://api.connectdial.com").rstrip("/")
    return f"{base}/api/media/{quote(key, safe='/')}"


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
    )


def _iter_streaming_body(body, chunk_size: int = CHUNK_SIZE) -> Iterable[bytes]:
    try:
        for chunk in body.iter_chunks(chunk_size=chunk_size):
            if chunk:
                yield chunk
    finally:
        body.close()


def storage_object_response(request, key: str, *, head_only: bool = False):
    """Return an HTTP response for one object in MinIO/S3 with Range support."""
    try:
        key = _clean_key(key)
    except ValueError:
        return HttpResponse(status=404)

    client = _s3_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME

    try:
        metadata = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return HttpResponse(status=404)
        return HttpResponse(status=502)

    size = int(metadata.get("ContentLength", 0))
    content_type = metadata.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream"
    etag = metadata.get("ETag")
    range_header = request.META.get("HTTP_RANGE")

    try:
        byte_range = parse_byte_range(range_header, size)
    except ValueError:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        response["Accept-Ranges"] = "bytes"
        return response

    common_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=86400",
        "Content-Type": content_type,
        "Content-Disposition": "inline",
    }
    if etag:
        common_headers["ETag"] = etag

    if byte_range:
        common_headers["Content-Length"] = str(byte_range.length)
        common_headers["Content-Range"] = f"bytes {byte_range.start}-{byte_range.end}/{size}"
        if head_only:
            response = HttpResponse(status=206)
        else:
            try:
                obj = client.get_object(
                    Bucket=bucket,
                    Key=key,
                    Range=f"bytes={byte_range.start}-{byte_range.end}",
                )
            except ClientError:
                return HttpResponse(status=502)
            response = StreamingHttpResponse(
                _iter_streaming_body(obj["Body"]),
                status=206,
                content_type=content_type,
            )
    else:
        common_headers["Content-Length"] = str(size)
        if head_only:
            response = HttpResponse(status=200)
        else:
            try:
                obj = client.get_object(Bucket=bucket, Key=key)
            except ClientError:
                return HttpResponse(status=502)
            response = StreamingHttpResponse(
                _iter_streaming_body(obj["Body"]),
                status=200,
                content_type=content_type,
            )

    for header, value in common_headers.items():
        response[header] = value
    return response
