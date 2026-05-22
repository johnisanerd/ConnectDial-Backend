from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from users.serializers import OnboardingSerializer, ProfileSerializer, CustomLoginSerializer
from users.models import FanPreference, Profile, Follow

User = get_user_model()

class MockLeagueTeamObject:
    def __init__(self, obj_id, name):
        self.id = obj_id
        self.name = name

class UsersSerializerTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="serializeruser",
            email="serializer@connectdial.com",
            password="SecureTestPassword123!"
        )
        self.mock_league = MockLeagueTeamObject(1, "Premier League")
        self.mock_team = MockLeagueTeamObject(5, "Arsenal")

    def test_custom_login_serializer_invalid_password(self):
        """Verifies clear reporting when verification keys are omitted."""
        serializer = CustomLoginSerializer(data={"username": "serializeruser", "password": ""})
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_onboarding_fan_account_requires_preferences(self):
        """Validates that a fan registration enforces team preference choices."""
        data = {
            "account_type": "fan",
            "fan_preferences": [],
            "append_mode": False
        }
        serializer = OnboardingSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_profile_counts_evaluation(self):
        """Validates calculation rules for counters inside serial maps."""
        user2 = User.objects.create_user(username="followeruser", email="f@cd.com", password="pwd")
        Follow.objects.create(follower=user2, followed=self.user)

        profile = Profile.objects.get(user=self.user)
        serializer = ProfileSerializer(instance=profile)
        
        self.assertEqual(serializer.data["followers_count"], 1)
        self.assertEqual(serializer.data["following_count"], 0)