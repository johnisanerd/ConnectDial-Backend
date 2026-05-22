from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from users.models import Profile, OTPCode, LoginHistory, AuditLog

User = get_user_model()

class UsersModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testmodeluser",
            email="modeltest@connectdial.com",
            password="SecureTestPassword123!"
        )

    def test_profile_auto_creation_via_signal(self):
        """Verifies that the post_save signal auto-provisions a Profile instance."""
        profile = Profile.objects.filter(user=self.user).first()
        self.assertIsNotNone(profile)
        self.assertFalse(profile.two_fa_enabled)
        self.assertFalse(profile.email_verified)

    def test_otp_code_generation_and_expiry(self):
        """Validates general-purpose OTP lifespan calculations."""
        otp = OTPCode.generate_for(self.user, purpose="password_reset")
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())
        self.assertFalse(otp.is_expired())

        # Simulate time jump forward beyond 15 minutes
        otp.expires_at = timezone.now() - timedelta(seconds=1)
        otp.save()
        self.assertTrue(otp.is_expired())

    def test_login_history_nullable_ip_address(self):
        """Ensures login logs don't throw IntegrityErrors if IP mapping is empty."""
        history = LoginHistory.objects.create(
            user=self.user,
            ip_address=None,
            device_info="Mock Client Agent Suite",
            success=True
        )
        self.assertIsNone(history.ip_address)
        self.assertTrue(history.success)

    def test_audit_log_actions_validation(self):
        """Ensures tracked actions validate cleanly against designated labels."""
        log = AuditLog.objects.create(
            user=self.user,
            action="password_reset_completed",
            ip_address="127.0.0.1"
        )
        self.assertEqual(log.action, "password_reset_completed")