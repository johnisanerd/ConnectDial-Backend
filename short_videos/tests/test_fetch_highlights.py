import json
from datetime import date
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class FetchHighlightsCommandTests(SimpleTestCase):
    def setUp(self):
        # Sample mock API response data
        self.mock_highlights = [
            {
                "id": "hl_123",
                "type": "goals",
                "title": "Amazing Messi Goal",
                "match": {
                    "league": {"name": "La Liga"},
                    "homeTeam": {"name": "Barcelona"},
                    "awayTeam": {"name": "Real Madrid"},
                },
            }
        ]

        # Standard mock return for the import function
        self.mock_import_result = MagicMock()
        self.mock_import_result.created = 1
        self.mock_import_result.skipped = 0
        self.mock_import_result.errors = []

    @patch("short_videos.highlightly.HighlightlyClient")
    def test_missing_api_key_raises_command_error(self, mock_client_cls):
        """The command must fail if no API key is provided via settings or CLI."""
        with self.assertRaises(CommandError) as context:
            call_command("fetch_highlights")
        
        self.assertIn("No Highlightly API key found", str(context.exception))

    @override_settings(HIGHLIGHTLY_API_KEY="test-settings-key")
    @patch("short_videos.highlightly.get_or_create_system_user")
    @patch("short_videos.highlightly.import_highlights")
    @patch("short_videos.highlightly.HighlightlyClient")
    def test_successful_default_run(
        self, mock_client_cls, mock_import_highlights, mock_get_user
    ):
        """Verifies successful run using default configurations from settings."""
        # Setup mocks
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.get_highlights.return_value = self.mock_highlights
        mock_import_highlights.return_value = self.mock_import_result
        mock_get_user.return_value = "mock_system_user"

        # Execute command
        call_command("fetch_highlights")

        # Verify API client initialization and call
        mock_client_cls.assert_called_once_with(api_key="test-settings-key")
        mock_client_instance.get_highlights.assert_called_once_with(
            sport="football",  # Default fallback
            date=str(date.today()),
            league_id=None,
            league_name=None,
            country_code=None,
            limit=40,
            offset=0,
        )

        # Verify internal utility executions
        mock_get_user.assert_called_once()
        mock_import_highlights.assert_called_once_with(
            self.mock_highlights,
            system_user="mock_system_user",
            sport="football",
            fetch_thumbnails=True,  # Default when --no-thumbnails is absent
        )

    @override_settings(HIGHLIGHTLY_API_KEY="test-settings-key")
    @patch("short_videos.highlightly.import_highlights")
    @patch("short_videos.highlightly.HighlightlyClient")
    def test_custom_cli_arguments(self, mock_client_cls, mock_import_highlights):
        """Verifies that explicitly passed CLI parameters override settings/defaults."""
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.get_highlights.return_value = self.mock_highlights
        mock_import_highlights.return_value = self.mock_import_result

        call_command(
            "fetch_highlights",
            api_key="cli-override-key",
            sport="basketball",
            date="2026-05-20",
            league_name="NBA",
            league_id=5,
            country_code="US",
            limit=10,
            offset=20,
            no_thumbnails=True,
        )

        # Assert CLI overrides worked
        mock_client_cls.assert_called_once_with(api_key="cli-override-key")
        mock_client_instance.get_highlights.assert_called_once_with(
            sport="basketball",
            date="2026-05-20",
            league_id=5,
            league_name="NBA",
            country_code="US",
            limit=10,
            offset=20,
        )
        # Assert thumbnails parameter is properly inverted
        _, kwargs = mock_import_highlights.call_args
        self.assertFalse(kwargs["fetch_thumbnails"])

    @override_settings(HIGHLIGHTLY_API_KEY="test-key")
    @patch("short_videos.highlightly.HighlightlyClient")
    def test_dry_run_does_not_import(self, mock_client_cls):
        """Dry run should query the API and print outcomes, but skip DB mutations."""
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.get_highlights.return_value = self.mock_highlights

        with patch("short_videos.highlightly.import_highlights") as mock_import:
            call_command("fetch_highlights", dry_run=True)
            mock_import.assert_not_called()

    @override_settings(HIGHLIGHTLY_API_KEY="test-key")
    @patch("short_videos.highlightly.HighlightlyClient")
    def test_api_error_raises_command_error(self, mock_client_cls):
        """API client exceptions must be trapped and re-raised as a CommandError."""
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.get_highlights.side_effect = Exception("API Timeout")

        with self.assertRaises(CommandError) as context:
            call_command("fetch_highlights")

        self.assertIn("Highlightly API error: API Timeout", str(context.exception))

    @override_settings(HIGHLIGHTLY_API_KEY="test-key")
    @patch("short_videos.highlightly.import_highlights")
    @patch("short_videos.highlightly.HighlightlyClient")
    def test_empty_api_response(self, mock_client_cls, mock_import_highlights):
        """When zero highlights return, the command should gracefully exit without processing."""
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.get_highlights.return_value = []

        call_command("fetch_highlights")
        mock_import_highlights.assert_not_called()