from django.test import TestCase, override_settings, RequestFactory
from unittest.mock import patch, MagicMock
from users.adapters import GoogleIdTokenAdapter

class GoogleTokenAdapterTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(GOOGLE_CLIENT_ID="web_client_id_key_mock")
    @patch("users.adapters.google_id_token.verify_oauth2_token")
    def test_complete_login_valid_id_token(self, mock_verify):
        """Verifies client payload extraction maps cleanly to provider formats."""
        mock_verify.return_value = {
            "sub": "google-uid-12345",
            "email": "adaptertest@gmail.com",
            "email_verified": True,
            "given_name": "Titus",
            "family_name": "Kiptoo",
            "picture": "https://storage.googleapis.com/img.png"
        }

        mock_request = self.factory.post('/api/auth/google/', {
            "id_token": "valid_mocked_id_token_string"
        })
        mock_app = MagicMock()
        mock_token = MagicMock()

        adapter = GoogleIdTokenAdapter(mock_request)   # ← Fixed
        
        with patch.object(adapter.get_provider(), "sociallogin_from_response") as mock_social_login:
            adapter.complete_login(mock_request, mock_app, mock_token)
            mock_social_login.assert_called_once_with(
                mock_request,
                {
                    'sub': 'google-uid-12345',
                    'email': 'adaptertest@gmail.com',
                    'given_name': 'Titus',
                    'family_name': 'Kiptoo',
                    'picture': 'https://storage.googleapis.com/img.png',
                    'email_verified': True
                }
            )

    @patch("users.adapters.google_id_token.verify_oauth2_token")
    def test_complete_login_unverified_email_fails(self, mock_verify):
        """Ensures registration rejects users with unverified Google accounts."""
        mock_verify.return_value = {
            "email": "unverified@gmail.com",
            "email_verified": False
        }

        mock_request = self.factory.post('/api/auth/google/', {
            "id_token": "mock_token"
        })

        adapter = GoogleIdTokenAdapter(mock_request)   # ← Fixed
        
        with self.assertRaises(Exception) as context:
            adapter.complete_login(mock_request, MagicMock(), MagicMock())
        self.assertIn("Google email not verified", str(context.exception))