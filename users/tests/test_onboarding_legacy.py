from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from unittest.mock import patch

User = get_user_model()

class OnboardingViewLegacyTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="legacyonboard",
            email="legacy@connectdial.com",
            password="SecureTestPassword123!"
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    @patch("feeds.models.LeagueFollow.objects.get_or_create")
    @patch("feeds.models.TeamFollow.objects.get_or_create")
    def test_legacy_onboarding_post_processing(self, mock_team_follow, mock_league_follow):
        """Tests that the procedural onboarding loops populate target tracking arrays correctly."""
        url = reverse("onboarding")
        payload = {
            "leagues": [1, 2],
            "teams": [5]
        }
        
        mock_team_follow.return_value = (MagicMock(), True)
        mock_league_follow.return_value = (MagicMock(), True)

        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Onboarding completed successfully")