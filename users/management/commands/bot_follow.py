"""
bot_follow.py  —  Smart Social Graph Expansion
────────────────────────────────────────────────
Improvements:
  • Prioritises team-level matches over league-level (feels personal)
  • News/Org bots follow real users too (not just bots)
  • Mutual follow probability: if target already follows the bot, bot follows back
  • Caps total follows per bot per run (prevents spam)
  • Rate-limit friendly: 0.1s sleep per follow (vs 0.2s per loop)
"""

import random
import time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from users.models import Follow

User = get_user_model()

MAX_FOLLOWS_PER_BOT = 5   # per run — keeps growth organic


class Command(BaseCommand):
    help = 'Smart social graph expansion — bots follow based on shared team/league interests'

    def handle(self, *args, **options):
        bots = User.objects.filter(profile__is_bot=True)
        if not bots.exists():
            self.stdout.write(self.style.ERROR("No bots found. Run generate_bots first."))
            return

        self.stdout.write(f"👥 Building social graph for {bots.count()} bots...")
        total_new = 0

        for bot in bots:
            already_following = Follow.objects.filter(follower=bot).values_list('followed_id', flat=True)
            followed_count    = 0

            # ── Priority 1: Same TEAM fans (strongest affinity) ──────────────
            if bot.favorite_team:
                team_mates = (User.objects
                              .filter(favorite_team=bot.favorite_team)
                              .exclude(id=bot.id)
                              .exclude(id__in=already_following)
                              .order_by('?')[:3])
                for target in team_mates:
                    if followed_count >= MAX_FOLLOWS_PER_BOT:
                        break
                    _, created = Follow.objects.get_or_create(follower=bot, followed=target)
                    if created:
                        self.stdout.write(
                            f"  ⚽ @{bot.username} → @{target.username} "
                            f"[same team: {bot.favorite_team.name}]")
                        followed_count += 1
                        total_new      += 1
                        time.sleep(0.1)

            # ── Priority 2: Mutual follow back ──────────────────────────────
            # If someone (real user or bot) follows this bot, follow back
            followers_not_followed = (User.objects
                                      .filter(following__followed=bot)
                                      .exclude(id=bot.id)
                                      .exclude(id__in=already_following)
                                      .order_by('?')[:2])
            for target in followers_not_followed:
                if followed_count >= MAX_FOLLOWS_PER_BOT:
                    break
                if random.random() < 0.70:   # 70% chance to follow back
                    _, created = Follow.objects.get_or_create(follower=bot, followed=target)
                    if created:
                        self.stdout.write(
                            f"  🔁 @{bot.username} → @{target.username} [mutual follow-back]")
                        followed_count += 1
                        total_new      += 1
                        time.sleep(0.1)

            # ── Priority 3: Same LEAGUE fans (broad interest) ────────────────
            if followed_count < MAX_FOLLOWS_PER_BOT and bot.favorite_league:
                league_mates = (User.objects
                                .filter(favorite_league=bot.favorite_league)
                                .exclude(id=bot.id)
                                .exclude(id__in=already_following)
                                .order_by('?')[:(MAX_FOLLOWS_PER_BOT - followed_count)])
                for target in league_mates:
                    if followed_count >= MAX_FOLLOWS_PER_BOT:
                        break
                    _, created = Follow.objects.get_or_create(follower=bot, followed=target)
                    if created:
                        self.stdout.write(
                            f"  🌍 @{bot.username} → @{target.username} "
                            f"[same league: {bot.favorite_league.name}]")
                        followed_count += 1
                        total_new      += 1
                        time.sleep(0.1)

        self.stdout.write(self.style.SUCCESS(
            f"✅ Social graph expanded — {total_new} new follows added"))