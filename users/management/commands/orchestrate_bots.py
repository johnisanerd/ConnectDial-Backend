"""
orchestrate_bots.py  —  Master Bot Orchestration Script (2026 Edition)
═══════════════════════════════════════════════════════════════════════
Runs all bot management commands in the correct order with a cron-ready
schedule. Can be run directly OR called via Django management command.

QUICK START:
  python manage.py run_bot_orchestra
  
  OR schedule each command separately via cron (see CRON SCHEDULE below).

CRON SCHEDULE (recommended):
  # Post content every 2 hours for each league
  0 */2 * * * python manage.py bot_post "Saudi Pro League"
  0 */2 * * * python manage.py bot_post "Premier League"
  0 */2 * * * python manage.py bot_post "Champions League"
  0 */2 * * * python manage.py bot_post "FIFA World Cup"
  0 */2 * * * python manage.py bot_post "La Liga"
  0 */2 * * * python manage.py bot_post "NBA"

  # Post a Short every 4 hours
  0 */4 * * * python manage.py bot_shorts "Saudi Pro League"
  0 */4 * * * python manage.py bot_shorts "Premier League"
  0 */4 * * * python manage.py bot_shorts "FIFA World Cup"

  # Engage with recent posts every 90 minutes
  */90 * * * * python manage.py bot_engage

  # Grow social graph daily at 9am
  0 9 * * * python manage.py bot_follow

  # Clean old media every Monday at 2am
  0 2 * * 1 python manage.py clean_storage --days 7
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from leagues.models import League
import time


LEAGUE_POST_ORDER = [
    "Saudi Pro League",
    "Premier League",
    "Champions League",
    "FIFA World Cup",
    "La Liga",
    "Serie A",
    "NBA",
    "MLS",
    "Bundesliga",
    "Ligue 1",
]

SHORTS_LEAGUES = [
    "Saudi Pro League",
    "Premier League",
    "FIFA World Cup",
    "Champions League",
    "NBA",
]


class Command(BaseCommand):
    help = 'Master bot orchestration — runs all bot tasks in the correct order'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            choices=['full', 'post', 'engage', 'shorts', 'follow'],
            default='full',
            help='Which tasks to run'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview without writing to DB'
        )

    def handle(self, *args, **options):
        mode    = options['mode']
        dry_run = options.get('dry_run', False)

        self.stdout.write("═" * 60)
        self.stdout.write("🤖 ConnectDial Bot Orchestra — 2026 Edition")
        self.stdout.write("═" * 60)

        active_leagues = set(League.objects.values_list('name', flat=True))

        # 1. GENERATE / POST
        if mode in ('full', 'post'):
            self.stdout.write("\n📰 Phase 1: Posting content...")
            for league_name in LEAGUE_POST_ORDER:
                # Check league exists
                if not any(league_name.lower() in l.lower() for l in active_leagues):
                    self.stdout.write(f"  ⏭️  {league_name} not in DB — skipping")
                    continue
                try:
                    self.stdout.write(f"\n  📌 {league_name}")
                    kwargs = {'league_name': league_name, 'source': 'auto'}
                    if dry_run:
                        kwargs['dry_run'] = True
                    call_command('bot_post', **kwargs)
                    time.sleep(2)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ❌ bot_post {league_name}: {e}"))

        # 2. SHORTS
        if mode in ('full', 'shorts'):
            self.stdout.write("\n🎬 Phase 2: Posting Shorts...")
            for league_name in SHORTS_LEAGUES:
                if not any(league_name.lower() in l.lower() for l in active_leagues):
                    continue
                try:
                    self.stdout.write(f"\n  📌 Shorts: {league_name}")
                    kwargs = {'league_name': league_name}
                    if dry_run:
                        kwargs['dry_run'] = True
                    call_command('bot_shorts', **kwargs)
                    time.sleep(3)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ❌ bot_shorts {league_name}: {e}"))

        # 3. ENGAGE
        if mode in ('full', 'engage'):
            self.stdout.write("\n💬 Phase 3: Engaging with posts...")
            try:
                call_command('bot_engage')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ bot_engage: {e}"))

        # 4. FOLLOW
        if mode in ('full', 'follow'):
            self.stdout.write("\n👥 Phase 4: Growing social graph...")
            try:
                call_command('bot_follow')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ bot_follow: {e}"))

        self.stdout.write("\n" + "═" * 60)
        self.stdout.write(self.style.SUCCESS("✅ Bot orchestra cycle complete!"))
        self.stdout.write("═" * 60)