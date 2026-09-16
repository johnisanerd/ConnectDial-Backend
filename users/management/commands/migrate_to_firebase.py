"""Safely migrate referenced Django media from legacy MinIO to Firebase/GCS."""

from __future__ import annotations

import mimetypes
import shutil
import tempfile
from dataclasses import dataclass
from urllib.parse import urlparse

from botocore.exceptions import ClientError
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import FileField

from connectdial.firebase_storage import get_gcs_bucket
from connectdial.legacy_minio import get_legacy_s3_client


@dataclass
class MigrationStats:
    scanned: int = 0
    migrated: int = 0
    verified: int = 0
    skipped: int = 0
    missing_source: int = 0
    failed: int = 0


def _is_absolute_url(value: str) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _iter_media_fields(model_label: str | None = None):
    if model_label:
        try:
            model = apps.get_model(model_label)
        except (LookupError, ValueError) as exc:
            raise CommandError(f"Unknown model '{model_label}'. Use app_label.ModelName.") from exc
        models = [model]
    else:
        models = apps.get_models()

    for model in models:
        for field in model._meta.fields:
            if isinstance(field, FileField):
                yield model, field


def _source_metadata(client, key: str):
    return client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)


def _destination_size(blob):
    if not blob.exists():
        return None
    blob.reload()
    return int(blob.size or 0)


def _copy_object(source_client, bucket, key: str, source_size: int, content_type: str | None):
    response = source_client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
    body = response["Body"]
    try:
        # Large videos roll to disk automatically; images remain in memory.
        with tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024, mode="w+b") as temp:
            shutil.copyfileobj(body, temp, length=1024 * 1024)
            temp.seek(0)
            blob = bucket.blob(key)
            blob.upload_from_file(
                temp,
                size=source_size,
                content_type=content_type,
                rewind=False,
            )
    finally:
        body.close()


class Command(BaseCommand):
    help = (
        "Copy all database-referenced FileField/ImageField objects from legacy "
        "MinIO into the private Firebase Storage bucket without changing DB keys."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report copies without uploading.')
        parser.add_argument('--verify-only', action='store_true', help='Verify Firebase copies without uploading.')
        parser.add_argument('--model', help='Limit to one app_label.ModelName.')
        parser.add_argument('--limit', type=int, help='Stop after scanning N object references.')

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        verify_only = bool(options['verify_only'])
        model_label = options.get('model')
        limit = options.get('limit')

        if dry_run and verify_only:
            raise CommandError('--dry-run and --verify-only cannot be used together.')
        if limit is not None and limit <= 0:
            raise CommandError('--limit must be a positive integer.')

        source_client = get_legacy_s3_client()
        destination_bucket = get_gcs_bucket()
        stats = MigrationStats()
        seen_keys = set()
        stop = False

        for model, field in _iter_media_fields(model_label):
            if stop:
                break

            queryset = model._default_manager.exclude(**{f"{field.name}__isnull": True}).exclude(
                **{field.name: ""}
            )

            for pk, raw_value in queryset.values_list('pk', field.name).iterator(chunk_size=500):
                if limit is not None and stats.scanned >= limit:
                    stop = True
                    break

                stats.scanned += 1
                key = str(raw_value or '').strip().lstrip('/')
                label = f"{model._meta.label}.{field.name} pk={pk}"

                if not key or _is_absolute_url(key):
                    stats.skipped += 1
                    self.stdout.write(f"SKIP {label}: not a relative storage key")
                    continue

                # The same object can be referenced by multiple rows/fields. Copy once.
                if key in seen_keys:
                    stats.skipped += 1
                    self.stdout.write(f"SKIP {label}: duplicate reference {key}")
                    continue
                seen_keys.add(key)

                try:
                    source_meta = _source_metadata(source_client, key)
                    source_size = int(source_meta.get('ContentLength', 0))
                    content_type = source_meta.get('ContentType') or mimetypes.guess_type(key)[0]
                except ClientError as exc:
                    code = str(exc.response.get('Error', {}).get('Code', ''))
                    if code in {'404', 'NoSuchKey', 'NotFound'}:
                        stats.missing_source += 1
                        self.stderr.write(f"MISSING {label}: {key}")
                        continue
                    stats.failed += 1
                    self.stderr.write(f"ERROR {label}: source metadata failed: {exc}")
                    continue
                except Exception as exc:
                    stats.failed += 1
                    self.stderr.write(f"ERROR {label}: source metadata failed: {exc}")
                    continue

                try:
                    blob = destination_bucket.blob(key)
                    destination_size = _destination_size(blob)

                    if destination_size == source_size:
                        stats.verified += 1
                        self.stdout.write(f"OK {label}: already verified {key} ({source_size} bytes)")
                        continue

                    if verify_only:
                        stats.failed += 1
                        if destination_size is None:
                            self.stderr.write(f"MISSING DEST {label}: {key}")
                        else:
                            self.stderr.write(
                                f"SIZE MISMATCH {label}: {key} source={source_size} destination={destination_size}"
                            )
                        continue

                    if dry_run:
                        stats.migrated += 1
                        self.stdout.write(f"DRY RUN {label}: copy {key} ({source_size} bytes)")
                        continue

                    _copy_object(source_client, destination_bucket, key, source_size, content_type)
                    destination_size = _destination_size(destination_bucket.blob(key))
                    if destination_size != source_size:
                        stats.failed += 1
                        self.stderr.write(
                            f"VERIFY FAILED {label}: {key} source={source_size} destination={destination_size}"
                        )
                        continue

                    stats.migrated += 1
                    self.stdout.write(self.style.SUCCESS(f"COPIED {label}: {key} ({source_size} bytes)"))
                except Exception as exc:
                    stats.failed += 1
                    self.stderr.write(f"ERROR {label}: {key}: {exc}")

        summary = (
            f"scanned={stats.scanned} migrated={stats.migrated} verified={stats.verified} "
            f"skipped={stats.skipped} missing_source={stats.missing_source} failed={stats.failed}"
        )
        if stats.failed or stats.missing_source:
            self.stdout.write(self.style.WARNING(f"Firebase migration finished with warnings: {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Firebase migration complete: {summary}"))
