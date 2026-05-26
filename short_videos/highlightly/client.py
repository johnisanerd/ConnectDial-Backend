"""
ConnectDial — Highlightly API Client
=====================================
Thin wrapper around the Highlightly Sports API.
Base URL: https://sports.highlightly.net

Auth header required on every request:
    x-rapidapi-key: <your key>

Usage:
    client = HighlightlyClient(api_key="YOUR_KEY")
    highlights = client.get_highlights(sport="football", date="2026-05-25", limit=40)
"""

import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)

HIGHLIGHTLY_BASE_URL = "https://sports.highlightly.net"

SUPPORTED_SPORTS = [
    "football",
    "basketball",
    "hockey",
    "cricket",
    "rugby",
    "volleyball",
    "handball",
    "american-football",
    "baseball",
    "nba",
    "nfl",
    "nhl",
    "mlb",
]


class HighlightlyClient:
    """
    Minimal HTTP client for the Highlightly Sports API.

    Parameters
    ----------
    api_key : str   Your Highlightly (or RapidAPI) key.
    timeout : int   Request timeout in seconds (default 30).
    """

    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "x-rapidapi-key": api_key,
            "Content-Type": "application/json",
        })

    # ─────────────────────────────────────────────────────────
    # HIGHLIGHTS
    # ─────────────────────────────────────────────────────────

    def get_highlights(
        self,
        sport: str = "football",
        *,
        date: Optional[str] = None,
        league_id: Optional[int] = None,
        league_name: Optional[str] = None,
        home_team_id: Optional[int] = None,
        away_team_id: Optional[int] = None,
        home_team_name: Optional[str] = None,
        away_team_name: Optional[str] = None,
        country_code: Optional[str] = None,
        country_name: Optional[str] = None,
        match_id: Optional[int] = None,
        season: Optional[int] = None,
        timezone: str = "Etc/UTC",
        limit: int = 40,
        offset: int = 0,
    ) -> list[dict]:
        """
        Fetch highlights for a given sport.

        Returns a list of highlight dicts from the API.
        At least one of: date, leagueId, leagueName, homeTeamName,
        awayTeamName, homeTeamId, awayTeamId must be provided.
        """
        if sport not in SUPPORTED_SPORTS:
            raise ValueError(f"Unsupported sport '{sport}'. Choose from: {SUPPORTED_SPORTS}")

        params = {k: v for k, v in {
            "date":         date,
            "leagueId":     league_id,
            "leagueName":   league_name,
            "homeTeamId":   home_team_id,
            "awayTeamId":   away_team_id,
            "homeTeamName": home_team_name,
            "awayTeamName": away_team_name,
            "countryCode":  country_code,
            "countryName":  country_name,
            "matchId":      match_id,
            "season":       season,
            "timezone":     timezone,
            "limit":        limit,
            "offset":       offset,
        }.items() if v is not None}

        url = f"{HIGHLIGHTLY_BASE_URL}/{sport}/highlights"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        return data.get("data", data) if isinstance(data, dict) else data

    def get_highlight_by_id(self, sport: str, highlight_id: int) -> Optional[dict]:
        """Fetch a single highlight by its ID."""
        url = f"{HIGHLIGHTLY_BASE_URL}/{sport}/highlights/{highlight_id}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        return result[0] if isinstance(result, list) and result else result

    # ─────────────────────────────────────────────────────────
    # MATCHES
    # ─────────────────────────────────────────────────────────

    def get_matches(
        self,
        sport: str = "football",
        *,
        date: Optional[str] = None,
        league_id: Optional[int] = None,
        league_name: Optional[str] = None,
        country_code: Optional[str] = None,
        timezone: str = "Etc/UTC",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch matches for a sport/date."""
        params = {k: v for k, v in {
            "date":        date,
            "leagueId":    league_id,
            "leagueName":  league_name,
            "countryCode": country_code,
            "timezone":    timezone,
            "limit":       limit,
            "offset":      offset,
        }.items() if v is not None}

        url = f"{HIGHLIGHTLY_BASE_URL}/{sport}/matches"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("data", data) if isinstance(data, dict) else data

    # ─────────────────────────────────────────────────────────
    # LEAGUES
    # ─────────────────────────────────────────────────────────

    def get_leagues(
        self,
        sport: str = "football",
        *,
        league_name: Optional[str] = None,
        country_code: Optional[str] = None,
        season: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch league list for a sport."""
        params = {k: v for k, v in {
            "leagueName":  league_name,
            "countryCode": country_code,
            "season":      season,
            "limit":       limit,
            "offset":      offset,
        }.items() if v is not None}

        url = f"{HIGHLIGHTLY_BASE_URL}/{sport}/leagues"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("data", data) if isinstance(data, dict) else data