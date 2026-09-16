# Firebase Media Storage Design

**Date:** 2026-09-16  
**Project:** SportTribe / ConnectDial Backend

## Goal

Make Firebase Storage (the project's Google Cloud Storage bucket) the single permanent media store for SportTribe while preserving existing Django `FileField`/`ImageField` behavior, supporting private media URLs, maintaining smooth image/video delivery, and safely migrating all existing MinIO objects without deleting the originals during the first migration pass.

## Current State

The backend currently uses `storages.backends.s3boto3.S3Boto3Storage` as Django's default storage and points it at the internal MinIO service. Public clients are protected from the Docker-only hostname by an API media proxy. Firebase Admin and Google Cloud Storage libraries are already installed and some Highlightly import code writes directly to Firebase, but those writes use public object URLs rather than the standard Django storage abstraction.

The repository contains file/image fields in these models:

- `users.User.profile_image` -> `profiles/`
- `users.User.banner_image` -> `banners/`
- `leagues.League.logo` -> `league_logos/`
- `leagues.Team.logo` -> `team_logos/`
- `posts.Post.media_file` -> `post_media/`
- `posts.PostMedia.file` -> `post_media/`
- `short_videos.ShortVideo.video` -> Shorts storage path
- `short_videos.ShortVideo.thumbnail` -> `shorts/thumbnails/`

The existing `migrate_to_firebase` command only handles local `Post.media_file` files and assumes `.path` exists. It is insufficient for MinIO-backed objects.

## Architecture

### Primary storage

Django's `STORAGES["default"]` will use a Firebase/GCS-backed storage backend. The backend will authenticate using the existing Firebase service-account JSON file configured by `FIREBASE_CREDENTIALS_PATH`. The bucket name comes from `GS_BUCKET_NAME`.

New Django media uploads therefore continue to use normal `FileField.save()`, serializer uploads, admin uploads, Celery tasks, and model field APIs; only the underlying storage changes.

### Private media access

The bucket remains private. Media URLs returned by Django are signed Google Cloud Storage URLs with a configurable lifetime. The default signed URL lifetime is six hours so images and videos can be fetched and sought without exposing the bucket publicly.

`connectdial.media.build_media_url()` will use the storage backend's `.url()` implementation for relative object names. Existing absolute external URLs continue to pass through unchanged.

The legacy `/api/media/<key>` endpoint remains available during the transition. It will redirect to a fresh signed Firebase/GCS URL rather than proxying MinIO bytes through Django. This preserves compatibility with older app builds while avoiding unnecessary application-server bandwidth.

### Video processing

Celery continues to download storage-backed videos to temporary local files before invoking FFmpeg. Processed H.264/AAC videos and generated JPEG thumbnails are written back through Django's default storage backend. No code may depend on `FieldFile.path`.

The existing fast-start video processing flow remains intact, which allows Google Cloud Storage to satisfy HTTP Range requests directly for smooth seek/buffer behavior.

### Firebase initialization

A single shared Firebase/GCS initialization module will load service-account credentials and construct the storage client/bucket. Notification code and media code will use the same configurable credential path rather than hard-coding `firebase-service-account.json`.

### Highlightly imports

Highlightly media will stop calling `blob.public_url`. Imported files will be written to the same private bucket and stored in Django model fields as object keys. This removes the second, inconsistent public-media path.

## Migration Strategy

A replacement `migrate_to_firebase` management command will migrate every Django `FileField` and `ImageField` dynamically, rather than hard-coding selected models.

For each referenced object:

1. Read the database field's object key.
2. Check whether that key already exists in the Firebase bucket.
3. If it exists and size verification is enabled, compare object sizes and skip only when verification succeeds.
4. Otherwise read the object from the legacy MinIO bucket using a dedicated legacy S3 client.
5. Upload to Firebase using the exact same object key.
6. Verify the destination object exists and matches the source size.
7. Leave the database field unchanged because the object key has not changed.
8. Record migrated/skipped/failed counts.

The first migration pass never deletes from MinIO. A `--dry-run` mode reports what would be copied. An optional `--model` / `--limit` mode allows staged migration. A later separate cleanup can be considered only after production verification.

Objects that are missing from MinIO or already represented by absolute external URLs are reported and skipped without changing database records.

## Deployment

Required server environment values:

- `FIREBASE_CREDENTIALS_PATH`
- `GS_BUCKET_NAME`
- `FIREBASE_SIGNED_URL_TTL_SECONDS` (default `21600`)
- Legacy migration-only MinIO values remain available until migration is verified:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_STORAGE_BUCKET_NAME`
  - `AWS_S3_ENDPOINT_URL`

During migration, MinIO stays in `docker-compose.yml` and remains a dependency only for the migration window. After all referenced media is verified in Firebase and the app has been exercised in production, MinIO can be removed in a separate cleanup change.

## Security

- Service-account JSON must stay server-side and must never be bundled into the Android application.
- The bucket remains private.
- Signed media URLs expire.
- No `make_public()` calls are permitted.
- No Firebase credential file is committed to Git.

## Error Handling

- Missing/invalid credentials fail at startup with a clear configuration error when media storage is accessed.
- Migration failures are isolated per object and summarized at the end.
- A failed copy never changes the database field and never deletes the MinIO source.
- URL generation failures are logged and return `None`/legacy behavior rather than exposing an internal hostname.
- Video processing keeps its existing retry/status behavior.

## Testing

Tests must cover:

1. Firebase storage configuration becomes Django's default storage.
2. `build_media_url()` produces signed GCS URLs and never returns `minio:9000`.
3. Existing absolute external URLs are preserved.
4. Legacy `/api/media/<key>` redirects to signed Firebase URLs.
5. Migration preserves exact object keys.
6. Migration skips verified existing Firebase objects.
7. Migration copies missing MinIO objects and verifies size.
8. Migration does not delete source objects.
9. Dry-run performs no upload.
10. Video processing works with a remote storage-backed `FieldFile` and never uses `.path`.
11. Highlightly imports store object keys/private media rather than public URLs.
12. Firebase notification initialization uses the configured credential path.

## Rollout / Rollback

### Rollout

1. Back up the production database and MinIO volume.
2. Deploy code with Firebase as the default storage while MinIO remains available.
3. Run `migrate_to_firebase --dry-run`.
4. Run a small limited migration and verify images/videos in SportTribe.
5. Run the full migration.
6. Run verification mode and compare referenced keys with Firebase objects.
7. Exercise profile images, post images, Shorts upload, playback, thumbnails, and bot/highlight imports.
8. Keep MinIO untouched for a rollback window.
9. Remove MinIO only in a later change after verification.

### Rollback

If Firebase media delivery fails, switch Django's default storage back to the existing S3/MinIO backend. Because the migration does not delete or rename source objects and preserves database object keys, existing records remain compatible with MinIO.
