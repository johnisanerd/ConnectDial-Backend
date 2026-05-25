"""
Management command: fetch_highlights
=====================================
Pulls sport highlights from the Highlightly API and saves them to the
ShortVideo table. Designed to be run by a superadmin (cron / manual).

Updated: Supports automatic pagination to safely extract large media batches.
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
            help="Max highlights to fetch per individual API call (max 40).",
        )
        parser.add_argument(
            "--offset",
            default=0,
            type=int,
            help="Initial pagination offset start point.",
        )
        parser.add_argument(
            "--all-pages",
            action="store_true",
            dest="all_pages",
            help="Auto-paginate through all available pages matching criteria until exhausted.",
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
        
        # Determine execution loop rules
        current_offset = options["offset"]
        single_page_limit = min(options["limit"], 40)
        auto_paginate = options["all_pages"]
        
        # Track historical batch sums across cycles
        total_created = 0
        total_skipped = 0
        total_errors = []

        client = HighlightlyClient(api_key=api_key)
        system_user = None if options["dry_run"] else get_or_create_system_user()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Highlightly Import Process Started ===\n"
            f"  Sport       : {sport}\n"
            f"  Date        : {fetch_date}\n"
            f"  Base Limit  : {single_page_limit}\n"
            f"  Auto-Page   : {auto_paginate}\n"
            f"  Dry run     : {options['dry_run']}\n"
        ))

        # Max safety iterations to guard against malicious/broken APIs infinite-looping
        max_loops = 100 
        loop_count = 0

        while True:
            loop_count += 1
            if loop_count > max_loops:
                self.stdout.write(self.style.WARNING("Loop safeguard triggered. Exiting batching lifecycle."))
                break

            self.stdout.write(f" -> Fetching page at offset {current_offset}...")

            # ── Fetch from API ────────────────────────────────────────────────
            try:
                highlights = client.get_highlights(
                    sport=sport,
                    date=fetch_date,
                    league_id=options.get("league_id"),
                    league_name=options.get("league_name"),
                    country_code=options.get("country_code"),
                    limit=single_page_limit,
                    offset=current_offset,
                )
            except Exception as exc:
                raise CommandError(f"Highlightly API error on offset {current_offset}: {exc}") from exc

            fetched_count = len(highlights)
            self.stdout.write(f"    Fetched {fetched_count} records from API.")

            if not highlights:
                if loop_count == 1:
                    self.stdout.write(self.style.WARNING("No highlights returned. Nothing to import."))
                else:
                    self.stdout.write("No more highlights found. Stream reached its tail end.")
                break

            # ── Dry run Execution Page Block ──────────────────────────────────
            if options["dry_run"]:
                self.stdout.write(self.style.SUCCESS(f"    [DRY RUN] Page evaluation visualization:"))
                for h in highlights:
                    match = h.get("match", {}) or {}
                    league = (match.get("league") or {}).get("name", "?")
                    home   = (match.get("homeTeam") or {}).get("name", "?")
                    away   = (match.get("awayTeam") or {}).get("name", "?")
                    self.stdout.write(
                        f"      [{h.get('type','?')}] id={h.get('id')} | "
                        f"{home} vs {away} | {league} | {h.get('title','')[:60]}"
                    )
                
                total_created += fetched_count
            
            # ── Live Production Data Extraction ────────────────────────────────
            else:
                result = import_highlights(
                    highlights,
                    system_user=system_user,
                    sport=sport,
                    fetch_thumbnails=not options["no_thumbnails"],
                )
                
                total_created += result.created
                total_skipped += result.skipped
                if result.errors:
                    total_errors.extend(result.errors)

            # Break logic check 
            if not auto_paginate or fetched_count < single_page_limit:
                break
                
            # Advance structural array pointer
            current_offset += single_page_limit

        # ── Global Execution Batch Metrics Report ──────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Global Batch Execution Finalized:\n"
            f"  Total Processed Created : {total_created}\n"
            f"  Total Duplicates Skipped: {total_skipped}\n"
            f"  Total Validation Errors : {len(total_errors)}\n"
        ))

        if total_errors:
            self.stdout.write(self.style.ERROR("Errors Summary:"))
            for err in total_errors[:50]:  # Cap console display output print count
                self.stdout.write(f"  {json.dumps(err)}")