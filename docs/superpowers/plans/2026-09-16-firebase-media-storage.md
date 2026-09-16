# Firebase Media Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace MinIO as SportTribe's permanent Django media store with private Firebase/Google Cloud Storage, migrate all existing referenced objects safely, and preserve smooth signed-URL image/video delivery.

**Architecture:** Use a focused Firebase/GCS storage adapter as Django's default storage while retaining a legacy MinIO client only for migration. Django model fields keep storing relative object keys; serializers generate signed Firebase URLs, and old `/api/media/<key>` requests redirect to fresh signed URLs.

**Tech Stack:** Django, django-storages, google-cloud-storage, firebase-admin, boto3, Celery, FFmpeg, PostgreSQL, pytest/Django tests.

**Spec:** `docs/superpowers/specs/2026-09-16-firebase-media-storage-design.md`

## Global Constraints

- `https://api.connectdial.com` remains the production API domain.
- Firebase Storage is the permanent media store for all new and existing media.
- Firebase bucket remains private.
- Signed media URL TTL defaults to 21,600 seconds (6 hours).
- Existing database object keys are preserved.
- First migration pass never deletes from MinIO.
- Service-account credentials remain server-side and are never committed or shipped in the Android app.
- Video processing must not use `FieldFile.path`.
- MinIO remains available until migration verification is complete.

---

### Task 1: Centralize Firebase/GCS credentials and storage access

**Files:**
- Create: `connectdial/firebase_storage.py`
- Modify: `connectdial/settings.py`
- Test: `regression_tests/test_firebase_storage.py`

**Interfaces:**
- Produces: `get_gcs_credentials()`, `get_gcs_client()`, `get_gcs_bucket()`, `FirebaseMediaStorage`
- Consumes: `settings.FIREBASE_CREDENTIALS_PATH`, `settings.GS_BUCKET_NAME`, `settings.FIREBASE_SIGNED_URL_TTL_SECONDS`

- [ ] **Step 1: Write failing configuration/storage tests**

Create tests that override Firebase settings with a temporary credentials path and assert the default storage backend is `connectdial.firebase_storage.FirebaseMediaStorage`, with a six-hour URL TTL and no MinIO default backend.

- [ ] **Step 2: Run the tests and verify RED**

Run:
```bash
python manage.py test regression_tests.test_firebase_storage -v 2
```

Expected: FAIL because `connectdial.firebase_storage` does not exist and `STORAGES["default"]` still points to S3Boto3Storage.

- [ ] **Step 3: Implement the Firebase storage adapter**

Implement:
```python
from functools import lru_cache
from google.cloud import storage
from google.oauth2 import service_account
from storages.backends.gcloud import GoogleCloudStorage
from django.conf import settings

@lru_cache(maxsize=1)
def get_gcs_credentials():
    return service_account.Credentials.from_service_account_file(
        settings.FIREBASE_CREDENTIALS_PATH
    )

@lru_cache(maxsize=1)
def get_gcs_client():
    return storage.Client(
        project=get_gcs_credentials().project_id,
        credentials=get_gcs_credentials(),
    )

@lru_cache(maxsize=1)
def get_gcs_bucket():
    return get_gcs_client().bucket(settings.GS_BUCKET_NAME)

class FirebaseMediaStorage(GoogleCloudStorage):
    bucket_name = None
    file_overwrite = False
    default_acl = None
    querystring_auth = True

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("bucket_name", settings.GS_BUCKET_NAME)
        kwargs.setdefault("credentials", get_gcs_credentials())
        super().__init__(*args, **kwargs)
```

Update settings with:
```python
FIREBASE_CREDENTIALS_PATH = os.getenv(
    "FIREBASE_CREDENTIALS_PATH",
    str(BASE_DIR / "firebase-service-account.json"),
)
GS_BUCKET_NAME = os.getenv(
    "GS_BUCKET_NAME",
    "agrieldo-bc336.firebasestorage.app",
)
FIREBASE_SIGNED_URL_TTL_SECONDS = int(
    os.getenv("FIREBASE_SIGNED_URL_TTL_SECONDS", "21600")
)

STORAGES = {
    "default": {
        "BACKEND": "connectdial.firebase_storage.FirebaseMediaStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

Keep the AWS/MinIO settings temporarily, clearly labeled migration-only.

- [ ] **Step 4: Run configuration tests and full Django system check**

Run:
```bash
python manage.py test regression_tests.test_firebase_storage -v 2
python manage.py check
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add connectdial/firebase_storage.py connectdial/settings.py regression_tests/test_firebase_storage.py
git commit -m "feat: use Firebase Storage for Django media"
```

---

### Task 2: Generate private signed media URLs and preserve old media links

**Files:**
- Modify: `connectdial/firebase_storage.py`
- Modify: `connectdial/media.py`
- Modify: `connectdial/views.py`
- Test: `regression_tests/test_media_config.py`
- Test: `regression_tests/test_firebase_media_urls.py`

**Interfaces:**
- Produces: `signed_media_url(name: str) -> str`
- Updates: `build_media_url(file_field_or_name, request=None) -> Optional[str]`
- Legacy endpoint: `/api/media/<path:key>` returns HTTP redirect to signed Firebase URL

- [ ] **Step 1: Write failing URL tests**

Cover relative object names, absolute HTTPS URLs, URL quoting, expiration usage, no `minio:9000`, and legacy proxy redirect behavior.

- [ ] **Step 2: Run tests and verify RED**

```bash
python manage.py test regression_tests.test_firebase_media_urls regression_tests.test_media_config -v 2
```

Expected: FAIL because the current helper builds `/api/media/...` URLs and streams from MinIO.

- [ ] **Step 3: Implement signed URL generation**

Add:
```python
from datetime import timedelta

def signed_media_url(name: str) -> str:
    blob = get_gcs_bucket().blob(name.lstrip("/"))
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(
            seconds=settings.FIREBASE_SIGNED_URL_TTL_SECONDS
        ),
        method="GET",
    )
```

Change `build_media_url()` so:
- empty -> `None`
- absolute `http://` or `https://` -> unchanged
- relative key -> `signed_media_url(key)`
- never produces internal MinIO hostname

Change the legacy `media_proxy` view to validate the key and return `redirect(signed_media_url(key))`.

- [ ] **Step 4: Run tests**

```bash
python manage.py test regression_tests.test_firebase_media_urls regression_tests.test_media_config -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add connectdial/firebase_storage.py connectdial/media.py connectdial/views.py regression_tests/test_firebase_media_urls.py regression_tests/test_media_config.py
git commit -m "feat: serve private Firebase media with signed URLs"
```

---

### Task 3: Make Firebase Admin initialization consistent

**Files:**
- Create: `connectdial/firebase_admin.py`
- Modify: `notifications/utils.py`
- Modify: `notifications/tasks.py`
- Test: `regression_tests/test_firebase_admin_config.py`

**Interfaces:**
- Produces: `get_firebase_app()`
- Uses the same `FIREBASE_CREDENTIALS_PATH` and `GS_BUCKET_NAME` as media storage

- [ ] **Step 1: Write failing initialization tests**

Assert notification modules do not hard-code `BASE_DIR / "firebase-service-account.json"` and initialization is idempotent.

- [ ] **Step 2: Run RED**

```bash
python manage.py test regression_tests.test_firebase_admin_config -v 2
```

Expected: FAIL because both notification modules initialize Firebase independently/hard-code credential paths.

- [ ] **Step 3: Implement shared initialization**

Create:
```python
import firebase_admin
from firebase_admin import credentials
from django.conf import settings

def get_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    return firebase_admin.initialize_app(
        cred,
        {"storageBucket": settings.GS_BUCKET_NAME},
    )
```

Call this helper before FCM `messaging.send()` rather than initializing at module import.

- [ ] **Step 4: Run tests**

```bash
python manage.py test regression_tests.test_firebase_admin_config -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add connectdial/firebase_admin.py notifications/utils.py notifications/tasks.py regression_tests/test_firebase_admin_config.py
git commit -m "refactor: centralize Firebase Admin initialization"
```

---

### Task 4: Normalize Highlightly imports to private Django storage

**Files:**
- Modify: `short_videos/highlightly/importer.py`
- Test: `short_videos/tests/test_fetch_highlights.py`
- Create: `regression_tests/test_highlightly_firebase_storage.py`

**Interfaces:**
- Highlightly stores relative object keys in `ShortVideo.video` / `ShortVideo.thumbnail`
- No `blob.public_url`, `make_public()`, or public ACL

- [ ] **Step 1: Write failing tests**

Assert imported video and thumbnail values are object keys and Firebase public URLs are not embedded in captions/model fields.

- [ ] **Step 2: Run RED**

```bash
python manage.py test regression_tests.test_highlightly_firebase_storage -v 2
```

Expected: FAIL because importer currently returns `blob.public_url` and stores `firebase_url:` metadata.

- [ ] **Step 3: Replace direct public uploads with Django storage writes**

Use `default_storage.save()` or model field `.save()` with `File`/`ContentFile`. Save:
```text
shorts/highlights/<highlight_id>.mp4
shorts/highlights/thumbs/<highlight_id>.jpg
```
as relative keys. Remove `firebase_url:` caption lines for newly imported objects.

- [ ] **Step 4: Run Highlightly tests**

```bash
python manage.py test regression_tests.test_highlightly_firebase_storage short_videos.tests.test_fetch_highlights -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add short_videos/highlightly/importer.py short_videos/tests/test_fetch_highlights.py regression_tests/test_highlightly_firebase_storage.py
git commit -m "refactor: store imported shorts through private Firebase storage"
```

---

### Task 5: Build safe MinIO-to-Firebase migration utilities

**Files:**
- Create: `connectdial/legacy_minio.py`
- Replace: `users/management/commands/migrate_to_firebase.py`
- Test: `regression_tests/test_migrate_to_firebase.py`

**Interfaces:**
- Produces: `get_legacy_s3_client()`
- Command options: `--dry-run`, `--model app_label.ModelName`, `--limit N`, `--verify-only`
- Dynamic discovery: all installed Django `FileField` and `ImageField` model fields

- [ ] **Step 1: Write failing migration tests**

Use fake source/destination clients to verify:
- exact object key preservation
- existing destination objects are skipped after size verification
- missing destination is copied
- source is never deleted
- database field remains unchanged
- dry-run does not upload
- missing source is reported without database mutation
- dynamic FileField discovery includes the eight currently known media fields

- [ ] **Step 2: Run RED**

```bash
python manage.py test regression_tests.test_migrate_to_firebase -v 2
```

Expected: FAIL because the existing command only checks local `Post.media_file.path`.

- [ ] **Step 3: Implement legacy MinIO client**

Create a boto3 client from migration-only AWS settings:
```python
def get_legacy_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
```

- [ ] **Step 4: Implement dynamic migration command**

Discover fields:
```python
from django.apps import apps
from django.db.models import FileField

for model in apps.get_models():
    for field in model._meta.fields:
        if isinstance(field, FileField):
            ...
```

For each relative object key:
- skip blank/absolute URL
- `head_object` in MinIO
- `blob.exists()` / reload in Firebase
- copy via streaming body into `blob.upload_from_file(..., rewind=True)`
- verify destination size
- never delete source
- do not modify model field when the key is preserved

- [ ] **Step 5: Run migration tests**

```bash
python manage.py test regression_tests.test_migrate_to_firebase -v 2
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add connectdial/legacy_minio.py users/management/commands/migrate_to_firebase.py regression_tests/test_migrate_to_firebase.py
git commit -m "feat: migrate all MinIO media safely to Firebase"
```

---

### Task 6: Verify video processing against remote Firebase storage

**Files:**
- Modify only if tests reveal a defect: `short_videos/tasks.py`
- Test: `regression_tests/test_firebase_video_processing.py`

**Interfaces:**
- `process_short_video(video_pk)` opens remote input with `FieldFile.open("rb")`
- uploads processed video and thumbnail through Django storage
- never accesses `FieldFile.path`

- [ ] **Step 1: Write a regression test with a path-less storage stub**

The stub must raise if `.path` is requested and must support `open`, `save`, and `delete`.

- [ ] **Step 2: Run RED/GREEN baseline**

```bash
python manage.py test regression_tests.test_firebase_video_processing -v 2
```

If the existing implementation already passes, keep production code unchanged and retain the regression test.

- [ ] **Step 3: If required, make only the minimal remote-storage fix**

Keep temporary local FFmpeg input/output handling and field `.open()`/`.save()` behavior.

- [ ] **Step 4: Run video tests**

```bash
python manage.py test regression_tests.test_firebase_video_processing -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add short_videos/tasks.py regression_tests/test_firebase_video_processing.py
git commit -m "test: guarantee Firebase-compatible video processing"
```

---

### Task 7: Prepare migration-safe Docker deployment

**Files:**
- Modify: `docker-compose.yml`
- Modify/Create: `.env.example`
- Create: `docs/firebase-media-migration.md`
- Test: `regression_tests/test_media_config.py`

**Interfaces:**
- Web/Celery receive Firebase credential path and bucket settings from `.env`
- MinIO remains running until verification is complete

- [ ] **Step 1: Document the exact environment contract**

Include:
```dotenv
FIREBASE_CREDENTIALS_PATH=/app/firebase-service-account.json
GS_BUCKET_NAME=agrieldo-bc336.firebasestorage.app
FIREBASE_SIGNED_URL_TTL_SECONDS=21600

# migration-only until MinIO retirement
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=connectdial-media
AWS_S3_ENDPOINT_URL=http://minio:9000
```

Mount the credential JSON read-only into `web`, `celery_worker`, and `celery_beat` if it is not already baked/mounted another way.

- [ ] **Step 2: Keep MinIO dependency only for migration window**

Do not remove MinIO in this task. Label its settings/services as legacy migration dependencies.

- [ ] **Step 3: Add migration runbook**

Document:
```bash
docker compose exec web python manage.py migrate_to_firebase --dry-run
docker compose exec web python manage.py migrate_to_firebase --limit 20
docker compose exec web python manage.py migrate_to_firebase --verify-only
docker compose exec web python manage.py migrate_to_firebase
docker compose exec web python manage.py migrate_to_firebase --verify-only
```

Also document database/MinIO backup steps and rollback by restoring S3Boto3Storage.

- [ ] **Step 4: Validate compose/config**

```bash
docker compose config >/tmp/sporttribe-compose.yml
python manage.py check
```

Expected: both commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example docs/firebase-media-migration.md regression_tests/test_media_config.py
git commit -m "docs: add Firebase media migration deployment workflow"
```

---

### Task 8: Full verification before release

**Files:** No production changes unless a test identifies a defect.

- [ ] **Step 1: Run the focused Firebase/media suites**

```bash
python manage.py test   regression_tests.test_firebase_storage   regression_tests.test_firebase_media_urls   regression_tests.test_firebase_admin_config   regression_tests.test_highlightly_firebase_storage   regression_tests.test_migrate_to_firebase   regression_tests.test_firebase_video_processing   regression_tests.test_media_config   short_videos.tests.test_fetch_highlights   -v 2
```

Expected: 0 failures.

- [ ] **Step 2: Run Django checks**

```bash
python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 3: Compile Python source**

```bash
python -m compileall -q connectdial users posts leagues short_videos notifications
```

Expected: exit 0.

- [ ] **Step 4: Validate deployment YAML**

```bash
docker compose config >/tmp/sporttribe-compose.yml
```

Expected: exit 0.

- [ ] **Step 5: Verify no internal/public-storage leaks**

```bash
grep -RniE   'blob\.public_url|make_public\(|MEDIA_URL.*minio|http://minio:9000.*MEDIA_URL'   connectdial users posts leagues short_videos notifications   --include='*.py'
```

Expected: no active production matches that expose media publicly or build client URLs from MinIO. Migration-only MinIO client references are allowed.

- [ ] **Step 6: Commit any final test-only adjustments**

```bash
git status --short
```

Only commit if verification required changes.
