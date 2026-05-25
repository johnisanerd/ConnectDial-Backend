"""
Management command: fetch_highlights
=====================================
Pulls sport highlights from the Highlightly API and saves them to the
ShortVideo table.  Designed to be run by a superadmin (cron / manual).

Usage examples
──────────────
# Today's football highlights (default)
python manage.py fetch_highlights

# Specific sport + date
python manage.py fetch_highlights --sport basketball --date 2026-05-20

# Filter by league
python manage.py fetch_highlights --sport football --league-name "Premier League"

# Limit & paginate
python manage.py fetch_highlights --limit 40 --offset 0

# Dry-run (print what would be imported, don't save)
python manage.py fetch_highlights --dry-run

Environment / settings required
────────────────────────────────
Add to your Django settings:

    HIGHLIGHTLY_API_KEY = "your-key-here"   # required
    HIGHLIGHTLY_SPORT   = "football"        # optional default
"""

import json
import logging
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch sport highlights from Highlightly API and store them as ShortVideo records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sport",
            default=None,
            help="Sport slug (football, basketball, cricket, etc.). "
                 "Falls back to settings.HIGHLIGHTLY_SPORT or 'football'.",
        )
        parser.add_argument(
            "--date",
            default=None,
            help="Date in YYYY-MM-DD format. Defaults to today.",
        )
        parser.add_argument(
            "--league-name",
            default=None,
            dest="league_name",
            help="Filter by league name (e.g. 'Premier League').",
        )
        parser.add_argument(
            "--league-id",
            default=None,
            type=int,
            dest="league_id",
            help="Filter by Highlightly league ID.",
        )
        parser.add_argument(
            "--country-code",
            default=None,
            dest="country_code",
            help="ISO 3166 country code filter (e.g. 'GB', 'DE').",
        )
        parser.add_argument(
            "--limit",
            default=40,
            type=int,
            help="Max highlights to fetch per call (max 40).",
        )
        parser.add_argument(
            "--offset",
            default=0,
            type=int,
            help="Pagination offset.",
        )
        parser.add_argument(
            "--no-thumbnails",
            action="store_true",
            dest="no_thumbnails",
            help="Skip thumbnail downloads (faster, less bandwidth).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Fetch from API and print results without saving to DB.",
        )
        parser.add_argument(
            "--api-key",
            default=None,
            dest="api_key",
            help="Override settings.HIGHLIGHTLY_API_KEY for this run.",
        )

    def handle(self, *args, **options):
        from short_videos.highlightly import (
            HighlightlyClient,
            import_highlights,
            get_or_create_system_user,
        )

        # ── Resolve API key ───────────────────────────────────────────────
        api_key = (
            options.get("api_key")
            or getattr(settings, "HIGHLIGHTLY_API_KEY", None)
        )
        if not api_key:
            raise CommandError(
                "No Highlightly API key found. "
                "Set HIGHLIGHTLY_API_KEY in settings or pass --api-key."
            )

        sport = (
            options.get("sport")
            or getattr(settings, "HIGHLIGHTLY_SPORT", "football")
        )

        fetch_date = options.get("date") or str(date.today())

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Highlightly Import ===\n"
            f"  Sport  : {sport}\n"
            f"  Date   : {fetch_date}\n"
            f"  Limit  : {options['limit']}  Offset: {options['offset']}\n"
            f"  Dry run: {options['dry_run']}\n"
        ))

        # ── Fetch from API ────────────────────────────────────────────────
        client = HighlightlyClient(api_key=api_key)

        try:
            highlights = client.get_highlights(
                sport=sport,
                date=fetch_date,
                league_id=options.get("league_id"),
                league_name=options.get("league_name"),
                country_code=options.get("country_code"),
                limit=min(options["limit"], 40),
                offset=options["offset"],
            )
        except Exception as exc:
            raise CommandError(f"Highlightly API error: {exc}") from exc

        self.stdout.write(f"  Fetched {len(highlights)} highlights from API.\n")

        if not highlights:
            self.stdout.write(self.style.WARNING("No highlights returned. Nothing to import."))
            return

        # ── Dry run ───────────────────────────────────────────────────────
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("\n[DRY RUN] Would import:"))
            for h in highlights:
                match = h.get("match", {}) or {}
                league = (match.get("league") or {}).get("name", "?")
                home   = (match.get("homeTeam") or {}).get("name", "?")
                away   = (match.get("awayTeam") or {}).get("name", "?")
                self.stdout.write(
                    f"  [{h.get('type','?')}] id={h.get('id')} | "
                    f"{home} vs {away} | {league} | {h.get('title','')[:60]}"
                )
            return

        # ── Import ────────────────────────────────────────────────────────
        system_user = get_or_create_system_user()

        result = import_highlights(
            highlights,
            system_user=system_user,
            sport=sport,
            fetch_thumbnails=not options["no_thumbnails"],
        )

        # ── Report ────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Import complete:\n"
            f"  Created : {result.created}\n"
            f"  Skipped : {result.skipped}  (already in DB)\n"
            f"  Errors  : {len(result.errors)}\n"
        ))

        if result.errors:
            self.stdout.write(self.style.ERROR("Errors:"))
            for err in result.errors:
                self.stdout.write(f"  {json.dumps(err)}")