# Firebase Media Static Verification

This package was statically verified in the ChatGPT build environment on 2026-09-16.

## Passed

- Python bytecode compilation for `connectdial`, `users`, `posts`, `leagues`, `short_videos`, `notifications`, and `regression_tests`.
- 18 source-level regression tests covering Firebase default storage, signed media URLs, legacy redirects, Highlightly private storage, dynamic MinIO migration, remote-safe video processing, Docker credential mounts, API domain, and existing media regressions.
- No Git conflict markers in production Python files.
- No active `S3Boto3Storage`, `blob.public_url`, `make_public()`, or hard-coded public `storage.googleapis.com/connect-c894b...` production path.
- No remote-media `FieldFile.path` usage in production code.
- No Firebase service-account JSON is included in the package.
- Docker Compose YAML parses successfully with the Firebase credential mount on `web`, `celery_worker`, and `celery_beat`.

## Runtime verification still required on the deployment server

The build environment did not have Django/Firebase dependencies installed and outbound package resolution was unavailable, so Django runtime tests and a real Firebase upload could not be executed here.

After deploying on the server, run:

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py migrate_to_firebase --dry-run
docker compose exec web python manage.py migrate_to_firebase --limit 20
docker compose exec web python manage.py migrate_to_firebase --verify-only --limit 20
```

Then exercise image upload/display and Short upload/playback/seek on a real device before running the full migration.
