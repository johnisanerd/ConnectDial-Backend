"""Firebase/Google Cloud Storage integration for SportTribe media.

Firebase Storage is backed by Google Cloud Storage.  This module centralises
service-account loading, bucket access and signed private media URLs so every
Django FileField/ImageField can use the same storage implementation.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from google.cloud import storage
from google.oauth2 import service_account
from storages.backends.gcloud import GoogleCloudStorage


def get_firebase_credentials_path() -> Path:
    path = Path(settings.FIREBASE_CREDENTIALS_PATH).expanduser()
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    if not path.exists() or not path.is_file():
        raise ImproperlyConfigured(
            f"Firebase service-account file not found: {path}. "
            "Set FIREBASE_CREDENTIALS_PATH to a readable server-side JSON file."
        )
    return path


@lru_cache(maxsize=1)
def get_gcs_credentials():
    """Return signing-capable service-account credentials for Firebase/GCS."""
    return service_account.Credentials.from_service_account_file(
        str(get_firebase_credentials_path())
    )


@lru_cache(maxsize=1)
def get_gcs_client():
    credentials = get_gcs_credentials()
    project_id = getattr(credentials, "project_id", None)
    return storage.Client(project=project_id, credentials=credentials)


@lru_cache(maxsize=1)
def get_gcs_bucket():
    bucket_name = getattr(settings, "GS_BUCKET_NAME", "").strip()
    if not bucket_name:
        raise ImproperlyConfigured("GS_BUCKET_NAME must be configured for Firebase Storage.")
    return get_gcs_client().bucket(bucket_name)


def _clean_object_name(name: str) -> str:
    value = (name or "").strip().lstrip("/")
    if not value:
        raise ValueError("empty media object name")

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        raise ValueError("absolute URL is not a Firebase object name")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("invalid Firebase object name")
    return value


def signed_media_url(name: str) -> str:
    """Create a short-lived private HTTPS URL for a Firebase/GCS object."""
    object_name = _clean_object_name(name)
    blob = get_gcs_bucket().blob(object_name)
    ttl = max(60, int(getattr(settings, "FIREBASE_SIGNED_URL_TTL_SECONDS", 21600)))
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=ttl),
        method="GET",
    )


class FirebaseMediaStorage(GoogleCloudStorage):
    """Django storage backend for the private Firebase Storage bucket."""

    file_overwrite = False
    default_acl = None
    querystring_auth = True

    def __init__(self, *args, **kwargs):
        # bucket_name and credentials are supported constructor settings across
        # django-storages GCS versions. Other privacy behaviour is enforced on
        # the instance after initialisation and by our overridden url().
        kwargs.setdefault("bucket_name", settings.GS_BUCKET_NAME)
        kwargs.setdefault("credentials", get_gcs_credentials())
        super().__init__(*args, **kwargs)
        self.file_overwrite = False
        self.default_acl = None
        self.querystring_auth = True

    def url(self, name, parameters=None):
        # Do not use public ACLs/download tokens. Every URL is time-limited.
        return signed_media_url(name)
