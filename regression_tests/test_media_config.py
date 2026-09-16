import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class MediaRegressionTests(unittest.TestCase):
    def test_api_domain_is_allowed(self):
        settings = (ROOT / 'connectdial' / 'settings.py').read_text()
        self.assertIn("'api.connectdial.com'", settings)

    def test_google_web_client_id_has_sporttribe_default(self):
        settings = (ROOT / 'connectdial' / 'settings.py').read_text()
        self.assertIn('597689072930-lf6o7j50lqv8ro2qc4lluq06gribo16h.apps.googleusercontent.com', settings)

    def test_media_stream_does_not_redirect_to_storage_internal_url(self):
        streaming = (ROOT / 'short_videos' / 'streaming.py').read_text()
        self.assertNotIn('HttpResponseRedirect(file_url)', streaming)

    def test_short_upload_starts_as_processing_not_published(self):
        views = (ROOT / 'short_videos' / 'views.py').read_text()
        self.assertIn("status='processing'", views)

    def test_short_model_supports_processing_and_failed_states(self):
        models = (ROOT / 'short_videos' / 'models.py').read_text()
        self.assertIn("('processing', 'Processing')", models)
        self.assertIn("('failed', 'Failed')", models)

    def test_short_engagement_counters_are_not_double_incremented(self):
        views = (ROOT / 'short_videos' / 'views.py').read_text()
        # Signals own cached likes/comments/shares/views. The API views must not
        # increment the same counters a second time after model save/delete.
        self.assertNotIn("cached_views=F('cached_views') + 1", views)
        self.assertNotIn("cached_comments=F('cached_comments') + 1", views)
        self.assertNotIn("cached_shares=F('cached_shares') + 1", views)

    def test_feed_cache_is_busted_when_processing_video_becomes_published(self):
        signals = (ROOT / 'short_videos' / 'signals.py').read_text()
        self.assertIn("if instance.status != 'published':", signals)

    def test_debug_urlconf_does_not_require_local_media_root_for_s3_storage(self):
        urls = (ROOT / 'connectdial' / 'urls.py').read_text()
        self.assertNotIn('settings.MEDIA_ROOT', urls)


if __name__ == '__main__':
    unittest.main()
