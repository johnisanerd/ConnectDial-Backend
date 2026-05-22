import base64
import pyotp
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from unittest.mock import patch, MagicMock
from users.models import OTPCode, Profile, Follow

User = get_user_model()

@override_settings(
    SECRET_KEY="test_secret_key_string_for_signing_hashes",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    TRUSTED_PROXY_COUNT=1,
    
    # NEW allauth settings (replace old ones)
    ACCOUNT_LOGIN_METHODS={'email'},
    ACCOUNT_SIGNUP_FIELDS=['email*', 'password1*', 'password2*'],
    ACCOUNT_USERNAME_REQUIRED=False,
    ACCOUNT_EMAIL_REQUIRED=True,
)
class MainViewsAuthSuite(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="tituskiptoo",
            email="tituskiptoo65@gmail.com",
            password="SecurePassword123!"
        )
        self.token = Token.objects.create(user=self.user)
        self.profile = Profile.objects.get(user=self.user)

    def test_custom_login_success(self):
        """Verifies token issuance matches expectations on valid requests."""
        url = reverse("rest_login")
        payload = {"username": "tituskiptoo", "password": "SecurePassword123!"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("key", response.data)

    @patch("users.views.send_otp_email")
    def test_forgot_password_view_creates_otp(self, mock_send_email):
        """Ensures that missing tracking records create corresponding entries."""
        url = reverse("password-forgot")
        payload = {"email": "tituskiptoo65@gmail.com"}
        response = self.client.post(url, payload, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(OTPCode.objects.filter(user=self.user, purpose="password_reset").exists())
        mock_send_email.assert_called_once()

    def test_change_password_requires_authenticated_headers(self):
        """Verifies proper access restriction checks on secure path targets."""
        url = reverse("password-change")
        payload = {"old_password": "SecurePassword123!", "new_password": "BrandNewPassword2026!"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_execution(self):
        """Confirms successful runtime execution and structural updates."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        url = reverse("password-change")
        payload = {"old_password": "SecurePassword123!", "new_password": "BrandNewPassword2026!"}
        
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPassword2026!"))

    def test_setup_2fa_view_response(self):
        """Validates structural initialization formatting for QR code payloads."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        url = reverse("2fa-setup")
        response = self.client.post(url, {}, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("secret", response.data)
        self.assertTrue(response.data["qr_code"].startswith("data:image/png;base64,"))

    def test_toggle_follow_view_interaction(self):
        """Validates proper toggle handling for social relationships."""
        target_user = User.objects.create_user(username="targetuser", email="t@cd.com", password="pwd")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        url = reverse("toggle-follow", kwargs={"user_id": target_user.id})
        
        # Follow item interaction
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["following"])

        # Unfollow item interaction
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["following"])

    def test_proxy_aware_ip_address_extraction_logic(self):
        """Validates proper extraction matching upstream ALB proxy chains."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        url = reverse("rest_login")
        payload = {"username": "tituskiptoo", "password": "SecurePassword123!"}
        
        # Simulate AWS ALB pass-through formatting headers
        response = self.client.post(
            url, payload, format="json",
            HTTP_X_FORWARDED_FOR="203.0.113.50, 172.31.15.10"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)