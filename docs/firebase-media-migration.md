# SportTribe Firebase Media Migration Runbook

SportTribe now uses the private Firebase Storage / Google Cloud Storage bucket as Django's default media storage. MinIO remains available only so existing objects can be copied and verified before it is retired.

## 1. Back up before deployment

Back up PostgreSQL and the MinIO data volume before changing storage configuration:

```bash
docker compose exec -T db pg_dump -U gilly -d connectdial_db > connectdial_before_firebase.sql
docker run --rm -v connectdial-backend_minio_data:/source -v "$PWD":/backup alpine \
  sh -c 'cd /source && tar czf /backup/minio_before_firebase.tgz .'
```

Adjust the Docker volume name if `docker volume ls` shows a different Compose project prefix.

## 2. Put the Firebase service account on the server

Keep the JSON outside Git. The current Compose default expects it at `./firebase.json` and mounts it read-only at `/app/firebase-service-account.json`.

```bash
# If this prints firebase.json, the secret is currently tracked by Git:
git ls-files firebase.json

# If tracked, untrack it without deleting your local credentials:
git rm --cached firebase.json

chmod 600 firebase.json
```

`firebase.json` and `firebase-service-account.json` are both listed in `.gitignore`. Rotate the service-account key if it has ever been committed or shared.

Set the real Firebase Storage bucket in `.env`:

```dotenv
FIREBASE_CREDENTIALS_HOST_PATH=./firebase.json
FIREBASE_CREDENTIALS_PATH=/app/firebase-service-account.json
GS_BUCKET_NAME=agrieldo-bc336.firebasestorage.app
FIREBASE_SIGNED_URL_TTL_SECONDS=21600
PUBLIC_API_BASE_URL=https://api.connectdial.com
```

If Firebase Console shows a different bucket for the service account project, use that exact bucket name instead of the example above.

## 3. Deploy while keeping MinIO running

```bash
docker compose up -d --build
docker compose ps
```

Check Django/Celery startup before migration:

```bash
docker compose logs --tail=100 web
docker compose logs --tail=100 celery_worker
```

## 4. Inspect what will be migrated

```bash
docker compose exec web python manage.py migrate_to_firebase --dry-run
```

You can stage a small batch first:

```bash
docker compose exec web python manage.py migrate_to_firebase --limit 20
```

Or restrict the scan to one Django model:

```bash
docker compose exec web python manage.py migrate_to_firebase --model users.Profile --limit 20
```

The command discovers `FileField` and `ImageField` fields dynamically. It preserves each existing object key and never deletes the MinIO source.

## 5. Verify the staged batch

Open SportTribe and check profile images, banners, league/team logos, post images and videos, Shorts thumbnails and Short playback.

Then run verification:

```bash
docker compose exec web python manage.py migrate_to_firebase --verify-only --limit 20
```

## 6. Run the full migration

```bash
docker compose exec web python manage.py migrate_to_firebase
```

Then verify every database-referenced object:

```bash
docker compose exec web python manage.py migrate_to_firebase --verify-only
```

A clean verification should end with `failed=0` and `missing_source=0`.

## 7. Runtime checks

```bash
docker compose exec web python manage.py check
curl -fsS https://api.connectdial.com/api/health/
```

Use the app to test a new profile image, a new post image, a new Short upload, thumbnail display, video start, seek, pause/resume and replay. New model fields should contain relative object keys; API responses should contain signed `https://storage.googleapis.com/...` URLs (or the equivalent signed GCS host), never `http://minio:9000`.

## Rollback

Do not remove MinIO during the first deployment. If Firebase delivery has a production problem, revert the code/config to the previous `S3Boto3Storage` default backend. The migration preserves database keys and does not delete MinIO objects, so the old storage remains usable during the rollback window.

Remove the MinIO service/volume only in a later change after a successful full verification and an agreed retention period.

## Current deployment alignment (2026-09-16)

The supplied backend service-account JSON identifies Firebase project
`agrieldo-bc336`, so the media bucket configured for this deployment is:

```text
agrieldo-bc336.firebasestorage.app
```

Run the safe environment updater from the backend root:

```bash
python3 scripts/update_firebase_env.py
```

It preserves existing secret values, aligns Firebase/media and Google OAuth
client IDs, removes the obsolete `AWS_S3_CUSTOM_DOMAIN`, creates a strong
Django secret only when the existing value is a placeholder, and writes a
`.env.before-firebase` backup.

Do not remove the legacy MinIO endpoint/credentials until the
`migrate_to_firebase --verify-only` pass reports no missing source objects or
failed migrations.
