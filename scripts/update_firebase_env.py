#!/usr/bin/env python3
"""Safely update an existing SportTribe backend .env for Firebase media.

Existing secrets are preserved. The script only changes non-secret integration
settings, removes the obsolete AWS_S3_CUSTOM_DOMAIN client-media setting, and
creates a strong DJANGO_SECRET_KEY if the current value is blank/a placeholder.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ENV_PATH = Path(os.environ.get("SPORTTRIBE_ENV_PATH", ".env"))

UPDATES = {
    "PUBLIC_API_BASE_URL": "https://api.connectdial.com",
    "FIREBASE_CREDENTIALS_HOST_PATH": "./firebase.json",
    "FIREBASE_CREDENTIALS_PATH": "/app/firebase-service-account.json",
    "GS_BUCKET_NAME": "agrieldo-bc336.firebasestorage.app",
    "FIREBASE_SIGNED_URL_TTL_SECONDS": "21600",
    "GOOGLE_CLIENT_ID": "597689072930-lf6o7j50lqv8ro2qc4lluq06gribo16h.apps.googleusercontent.com",
    "GOOGLE_ANDROID_CLIENT_ID": "597689072930-67d9a06t10l30gi1rdtm5o0lr7sb2g06.apps.googleusercontent.com",
}

REMOVE = {"AWS_S3_CUSTOM_DOMAIN"}
PLACEHOLDER_SECRETS = {"", "your_secret_key_here", "replace-me", "changeme"}


def parse(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value
    return result


def main() -> None:
    if not ENV_PATH.exists():
        raise SystemExit(f"Environment file not found: {ENV_PATH}")

    original = ENV_PATH.read_text().splitlines()
    current = parse(original)

    updates = dict(UPDATES)
    if current.get("DJANGO_SECRET_KEY", "").strip() in PLACEHOLDER_SECRETS:
        updates["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(64)

    output: list[str] = []
    seen: set[str] = set()

    for raw in original:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            output.append(raw)
            continue

        key = raw.split("=", 1)[0].strip()
        if key in REMOVE:
            continue
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(raw)

    missing = [key for key in updates if key not in seen]
    if missing:
        output.extend(["", "# SportTribe Firebase media / OAuth alignment"])
        output.extend(f"{key}={updates[key]}" for key in missing)

    backup = ENV_PATH.with_name(ENV_PATH.name + ".before-firebase")
    if not backup.exists():
        backup.write_text("\n".join(original) + "\n")
        os.chmod(backup, 0o600)

    ENV_PATH.write_text("\n".join(output) + "\n")
    os.chmod(ENV_PATH, 0o600)

    print(f"Updated {ENV_PATH} without printing secret values.")
    print(f"Backup: {backup}")
    print("Firebase bucket: agrieldo-bc336.firebasestorage.app")
    print("Backend Google OAuth client IDs now match the SportTribe Android project.")
    print("Legacy MinIO credentials were preserved for migration/rollback.")


if __name__ == "__main__":
    main()
