"""
ConnectDial — Admin-only Highlightly Import API View
=====================================================
POST  /api/videos/admin/import-highlights/
GET   /api/videos/admin/import-highlights/preview/

Both endpoints require:
    - is_staff=True OR is_superuser=True
    - Valid authentication (token / session)

This view lets a superadmin trigger a Highlightly import without
SSH access.  Useful for backoffice dashboards or one-click CMS
buttons.

POST body (JSON)
────────────────
{
  "sport":        "football",          # required (default: settings.HIGHLIGHTLY_SPORT)
  "date":         "2026-05-25",        # optional (default: today)
  "league_name":  "Premier League",   # optional
  "league_id":    97798,              # optional
  "country_code": "GB",               # optional
  "limit":        40,                  # optional 1-40 (default 40)
  "offset":       0,                   # optional
  "fetch_thumbnails": true,            # optional (default true)
  "dry_run":      false                # optional — returns preview without saving
}

Success 200
───────────
{
  "status":  "ok",
  "dry_run": false,
  "result":  { "created": 12, "skipped": 3, "errors": [], "total_processed": 15 }
}

Dry-run 200
───────────
{
  "status":  "preview",
  "dry_run": true,
  "count":   15,
  "highlights": [ { "id": 1, "title": "...", ... }, ... ]
}

Errors
──────
401 — not authenticated
403 — authenticated but not staff/superuser
400 — bad request (missing/invalid fields)
502 — Highlightly API error
"""

import logging
from datetime import date

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class IsSuperAdminOrStaff(IsAuthenticated):
    """Allow only staff or superusers through."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return bool(request.user.is_staff or request.user.is_superuser)


class HighlightlyImportView(APIView):
    """
    Admin endpoint to pull highlights from Highlightly into ShortVideo.

    GET  → preview (no DB writes)
    POST → import (writes to DB unless dry_run=true)
    """

    permission_classes = [IsSuperAdminOrStaff]

    # ── GET: preview without importing ───────────────────────────────────────

    def get(self, request):
        """
        Preview what would be imported for today's date.
        Accepts same query params as POST body.
        """
        payload = {
            "sport":        request.query_params.get("sport"),
            "date":         request.query_params.get("date"),
            "league_name":  request.query_params.get("league_name"),
            "league_id":    request.query_params.get("league_id"),
            "country_code": request.query_params.get("country_code"),
            "limit":        request.query_params.get("limit", 40),
            "offset":       request.query_params.get("offset", 0),
            "dry_run":      True,
        }
        return self._handle(request, payload)

    # ── POST: import ─────────────────────────────────────────────────────────

    def post(self, request):
        return self._handle(request, request.data)

    # ── Core logic ────────────────────────────────────────────────────────────

    def _handle(self, request, payload):
        from short_videos.highlightly import (
            HighlightlyClient,
            import_highlights,
            get_or_create_system_user,
        )

        # ── API key ───────────────────────────────────────────────────────
        api_key = (
            payload.get("api_key")
            or getattr(settings, "HIGHLIGHTLY_API_KEY", None)
        )
        if not api_key:
            return Response(
                {"detail": "HIGHLIGHTLY_API_KEY is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Params ────────────────────────────────────────────────────────
        sport = (
            payload.get("sport")
            or getattr(settings, "HIGHLIGHTLY_SPORT", "football")
        )
        fetch_date = payload.get("date") or str(date.today())

        try:
            limit  = max(1, min(int(payload.get("limit", 40)), 40))
            offset = max(0, int(payload.get("offset", 0)))
        except (TypeError, ValueError) as exc:
            return Response({"detail": f"Invalid limit/offset: {exc}"}, status=400)

        dry_run           = str(payload.get("dry_run", "false")).lower() in ("true", "1", "yes")
        fetch_thumbnails  = str(payload.get("fetch_thumbnails", "true")).lower() not in ("false", "0", "no")
        league_id         = payload.get("league_id")
        league_name       = payload.get("league_name")
        country_code      = payload.get("country_code")

        logger.info(
            "HighlightlyImport requested by %s — sport=%s date=%s dry_run=%s",
            request.user.username, sport, fetch_date, dry_run,
        )

        # ── Fetch from API ────────────────────────────────────────────────
        client = HighlightlyClient(api_key=api_key)

        try:
            highlights = client.get_highlights(
                sport=sport,
                date=fetch_date,
                league_id=int(league_id) if league_id else None,
                league_name=league_name,
                country_code=country_code,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            logger.error("Highlightly API error: %s", exc)
            return Response(
                {"detail": f"Highlightly API error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ── Dry run ───────────────────────────────────────────────────────
        if dry_run:
            preview = [
                {
                    "id":     h.get("id"),
                    "type":   h.get("type"),
                    "title":  h.get("title"),
                    "source": h.get("source"),
                    "url":    h.get("url"),
                    "match": {
                        "home":   (h.get("match") or {}).get("homeTeam", {}).get("name"),
                        "away":   (h.get("match") or {}).get("awayTeam", {}).get("name"),
                        "league": ((h.get("match") or {}).get("league") or {}).get("name"),
                        "date":   (h.get("match") or {}).get("date"),
                    },
                }
                for h in highlights
            ]
            return Response({
                "status":     "preview",
                "dry_run":    True,
                "sport":      sport,
                "date":       fetch_date,
                "count":      len(highlights),
                "highlights": preview,
            })

        # ── Live import ───────────────────────────────────────────────────
        if not highlights:
            return Response({
                "status":  "ok",
                "dry_run": False,
                "message": "No highlights found for the given parameters.",
                "result":  {"created": 0, "skipped": 0, "errors": [], "total_processed": 0},
            })

        system_user = get_or_create_system_user()

        result = import_highlights(
            highlights,
            system_user=system_user,
            sport=sport,
            fetch_thumbnails=fetch_thumbnails,
        )

        return Response({
            "status":  "ok",
            "dry_run": False,
            "sport":   sport,
            "date":    fetch_date,
            "result":  result.to_dict(),
        })