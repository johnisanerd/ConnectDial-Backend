import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FirebaseStorageStaticRegressionTests(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text()

    def test_default_storage_uses_firebase_adapter(self):
        settings = self.read('connectdial/settings.py')
        self.assertIn('connectdial.firebase_storage.FirebaseMediaStorage', settings)
        self.assertIn('FIREBASE_SIGNED_URL_TTL_SECONDS', settings)

    def test_firebase_adapter_exists_and_generates_signed_urls(self):
        storage = self.read('connectdial/firebase_storage.py')
        self.assertIn('class FirebaseMediaStorage', storage)
        self.assertIn('generate_signed_url', storage)
        self.assertIn('get_gcs_bucket', storage)

    def test_client_media_helper_uses_firebase_not_minio(self):
        media = self.read('connectdial/media.py')
        self.assertIn('signed_media_url', media)
        self.assertNotIn('boto3.client(', media)
        self.assertNotIn('StreamingHttpResponse', media)

    def test_legacy_media_endpoint_redirects_to_signed_url(self):
        views = self.read('connectdial/views.py')
        self.assertIn('signed_media_url', views)
        self.assertIn('redirect(', views)

    def test_short_serializer_returns_direct_signed_storage_url(self):
        serializers = self.read('short_videos/serializers.py')
        self.assertIn('return _build_url(request, obj.video)', serializers)
        self.assertNotIn('return f"{base}/api/videos/shorts/{obj.pk}/stream/"', serializers)

    def test_notifications_share_configured_firebase_initializer(self):
        helper = self.read('connectdial/firebase_admin.py')
        utils = self.read('notifications/utils.py')
        tasks = self.read('notifications/tasks.py')
        self.assertIn('def get_firebase_app', helper)
        self.assertIn('get_firebase_app()', utils)
        self.assertIn('get_firebase_app()', tasks)
        self.assertNotIn("settings.BASE_DIR, 'firebase-service-account.json'", utils)
        self.assertNotIn("settings.BASE_DIR, 'firebase-service-account.json'", tasks)

    def test_highlightly_does_not_make_or_store_public_firebase_urls(self):
        importer = self.read('short_videos/highlightly/importer.py')
        self.assertNotIn('blob.public_url', importer)
        self.assertNotIn('firebase_url:', importer)
        self.assertIn('default_storage.save', importer)

    def test_migration_command_is_all_file_fields_and_non_destructive(self):
        command = self.read('users/management/commands/migrate_to_firebase.py')
        self.assertIn('apps.get_models()', command)
        self.assertIn('FileField', command)
        self.assertIn('--dry-run', command)
        self.assertIn('--verify-only', command)
        self.assertNotIn('.path', command)
        self.assertNotIn('delete_object', command)

    def test_video_processing_remains_remote_storage_safe(self):
        tasks = self.read('short_videos/tasks.py')
        self.assertIn('instance.video.open("rb")', tasks)
        self.assertNotIn('instance.video.path', tasks)

    def test_docker_mounts_firebase_credentials_for_runtime_services(self):
        compose = self.read('docker-compose.yml')
        self.assertGreaterEqual(compose.count(':/app/firebase-service-account.json:ro'), 3)


if __name__ == '__main__':
    unittest.main()
