"""Shared Firebase Admin SDK initialisation."""

from __future__ import annotations

import firebase_admin
from django.conf import settings
from firebase_admin import credentials

from connectdial.firebase_storage import get_firebase_credentials_path


def get_firebase_app():
    """Return the process-wide Firebase app, initialising it exactly once."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(str(get_firebase_credentials_path()))
        return firebase_admin.initialize_app(
            cred,
            {"storageBucket": settings.GS_BUCKET_NAME},
        )
