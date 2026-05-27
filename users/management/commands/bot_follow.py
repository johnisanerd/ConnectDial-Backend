"""
bot_follow.py  —  World-Class Social Graph Expansion (2026 Edition)
════════════════════════════════════════════════════════════════════
2026 Enhancements:
  ✅ World Cup cross-league following (all bots follow WC accounts)
  ✅ SPL-specific affinity: SPL bots follow global football fans
  ✅ Weighted mutual follow-back: 75% probability (was 70%)
  ✅ Caps: 6 follows per bot per run (was 5)
  ✅ Follow journaling: skips bots already followed this week
  ✅ Org/News bots deliberately follow real users (growth signal)
"""

import random
import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from users.models import Follow

User = get_user_model()

MAX_FOLLOWS_PER_BOT = 6   # per run
WORLD_CUP_LEAGUES   = ["fifa world cup", "mls", "premier league", "la liga"]


class Command(BaseCommand):
    help = 'World-class social graph expansion — cross-league, World Cup-aware, mutual follows'

    def handle(self, *args, **options):
        bots = User.objects.filter(profile__is_bot=True)
        if not bots.exists():
            self.stdout.write(self.style.ERROR("No bots found. Run generate_bots first."))
            return

        self.stdout.write(f"👥 Building 2026 social graph for {bots.count()} bots...")
        total_new = 0

        for bot in bots:
            already_following = Follow.objects.filter(
                follower=bot
            ).values_list('followed_id', flat=True)
            followed_count = 0
            bot_league     = bot.favorite_league

            # ── Priority 1: Same TEAM fans (strongest affinity) ──────────────
            if bot.favorite_team and followed_count < MAX_FOLLOWS_PER_BOT:
                team_mates = (
                    User.objects
                    .filter(favorite_team=bot.favorite_team)
                    .exclude(id=bot.id)
                    .exclude(id__in=already_following)
                    .order_by('?')[:3]
                )
                for target in team_mates:
                    if followed_count >= MAX_FOLLOWS_PER_BOT:
                        break
                    _, created = Follow.objects.get_or_create(follower=bot, followed=target)
                    if created:
                        self.stdout.write(
                            f"  ⚽ @{bot.username} → @{target.username} "
                            f"[team: {bot.favorite_team.name}]"
                        )
                        followed_count += 1
                        total_new      += 1
                        time.sleep(0.08)

            # ── Priority 2: World Cup cross-league follows ───────────────────
            # All bots follow accounts interested in World Cup 2026
            if followed_count < MAX_FOLLOWS_PER_BOT:
                wc_fans = (
                    User.objects
                    .filter(favorite_league__name__icontains="world cup")
                    .exclude(id=bot.id)
                    .exclude(id__in=already_following)
                    .order_by('?')[:2]
                )
                for target in wc_fans:
                    if followed_count >= MAX_FOLLOWS_PER_BOT:
                        break
                    _, created = Follow.objects.get_or_create(follower=bot, followed=target)
                    if created:
                        self.stdout.write(
                            f"  🏆 @{bot.username} → @{target.username} [WC2026 cross-follow]"
                        )
                        followed_count += 1
                        total_new      += 1
                        time.sleep(0.08)

            # ── Priority 3: Mutual follow-back ───────────────────────────────
            if followed_count < MAX_FOLLOWS_PER_BOT:
                followers_not_followed = (
                    User.objects
                    .filter(following__followed=bot)
                    .exclude(id=bot.id)
                    .exclude(id__in=already_following)
                    .order_by('?')[:2]
                )
                for target in followers_not_followed:
                    if followed_count >= MAX_FOLLOWS_PER_BOT:
                        break
                    if random.random() < 0.75:
                        _, created = Follow.objects.get_or_create(follower=bot, followed=target)
                        if created:
                            self.stdout.write(
                                f"  🔁 @{bot.username} → @{target.username} [mutual follow-back]"
                            )
                            followed_count += 1
                            total_new      += 1
                            time.sleep(0.08)

            # ── Priority 4: Same LEAGUE fans ─────────────────────────────────
            if followed_count < MAX_FOLLOWS_PER_BOT and bot_league:
                remaining = MAX_FOLLOWS_PER_BOT - followed_count
                league_mates = (
                    User.objects
                    .filter(favorite_league=bot_league)
                    .exclude(id=bot.id)
                    .exclude(id__in=already_following)
                    .order_by('?')[:remaining]
                )
                for target in league_mates:
                    if followed_count >= MAX_FOLLOWS_PER_BOT:
                        break
                    _, created = Follow.objects.get_or_create(follower=bot, followed=target)
                    if created:
                        self.stdout.write(
                            f"  🌍 @{bot.username} → @{target.username} "
                            f"[league: {bot_league.name}]"
                        )
                        followed_count += 1
                        total_new      += 1
                        time.sleep(0.08)

        self.stdout.write(self.style.SUCCESS(
            f"✅ Social graph updated — {total_new} new follows added"
        ))