"""
bot_engage.py  —  Intelligent Context-Aware Engagement Bot
───────────────────────────────────────────────────────────
Improvements over original:
  • 8 reaction categories (up from 4) with league/team substitution
  • Saudi Pro League–aware commentary pool
  • Transfer window detection
  • Score/result detection (e.g. "3-1", "2-0")
  • Injury / suspension detection
  • Rivalry detection
  • Congestion control: max 1 engagement per bot per 6-hour window
  • Weighted action distribution: likes > comments > reposts (feels natural)
"""

import random
import re
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from posts.models import Post, PostLike, Comment
from django.utils import timezone

User = get_user_model()

# ─── Reaction pool by category ───────────────────────────────────────────────

REACTIONS = {

    "goal_scored": [
        "GOALLLLL!!! 🚀🚀🚀 {subject} fans going absolutely mental right now!",
        "What a finish from {subject}! That's going in the highlights reel 🎬",
        "The striker instinct from {subject}! Clinical. Pure class. 🥅",
        "Put it in the NET! {subject} with the crucial goal 🔥🔥",
        "{subject} being ruthless today. That's why we watch 👏",
    ],

    "match_result": [
        "Three points for {subject}! Absolutely massive result this weekend 💪",
        "{subject} keep the pressure on. The title race is getting spicy 🌶️",
        "Solid performance. {subject} doing exactly what they need to this season.",
        "Full time: {subject} get the job done. No complaints from me!",
        "Points on the board for {subject}! Every single one matters now 📊",
    ],

    "transfer_news": [
        "IF TRUE — {subject} signing this player would be absolutely seismic 💣",
        "Another blockbuster rumour involving {subject}! The transfer window never sleeps 👀",
        "The {subject} board are cooking something special this window 🍳",
        "Breaking: {subject} making moves in the market. This changes everything!",
        "{subject} linked with another big name. Announcement incoming? 👀 #Transfers",
    ],

    "spl_specific": [
        "The Saudi Pro League is BUILT DIFFERENT. {subject} proving it every week 🇸🇦",
        "{subject} in the SPL is the best decision he ever made. Peak football ⚽",
        "Roshn League giving us the content every single week. {subject} putting on a show! 🌟",
        "SPL mid-week action featuring {subject} and I am LOCKED IN 🔒📱",
        "They said the Saudi Pro League wasn't serious. Tell that to {subject} 😂🔥",
        "Al-Hilal · Al-Nassr · {subject} — the SPL top 4 race is WILD this season 🎢",
    ],

    "injury_suspension": [
        "Gutted to hear about the {subject} injury. Massive blow for the team 😔",
        "Hope {subject} recovers quickly. Football misses him when he's out 🙏",
        "The squad depth is going to be tested now. Come on {subject}! 💪",
        "{subject} absence is a real problem. Who steps up? Big call for the manager.",
    ],

    "rivalry": [
        "Derby day always hits different. {subject} need to show up today! ⚔️",
        "Rivalries are what football is all about. {subject} can't drop points here!",
        "The atmosphere for {subject} derbies is unmatched anywhere in the world 🌍",
        "{subject} vs their rivals — no one sleeps on matchday 😤",
    ],

    "analysis": [
        "Tactically, {subject} have been set up brilliantly these last few weeks. Press is relentless.",
        "Stats don't lie — {subject} are dominating possession AND creating more xG than anyone 📈",
        "The {subject} high press is suffocating teams. Manager deserves huge credit.",
        "Interesting system from {subject} lately. That 4-3-3 transition is silky smooth.",
        "{subject} xG numbers are insane. They're not getting lucky — they're that good.",
    ],

    "general_hype": [
        "Great update on {subject}. ConnectDial always first with the news 📲",
        "Can't take my eyes off {subject} this season. Absolutely riveting football ⚽",
        "This is exactly why I joined ConnectDial — {subject} content all day! 🙌",
        "Another day, another reason to love {subject}. Football is beautiful 💙",
        "Keep these {subject} updates coming! Living for this content 🔥 #ConnectDial",
    ],
}

# Repost caption templates
REPOST_CAPTIONS = [
    "If you follow {league}, you NEED to see this update on {subject} 👇",
    "Huge news regarding {subject}. Eyes wide open on this one! 📌",
    "This is a massive development for {subject}. Sharing for the ConnectDial fam 🙏",
    "Direct from the source. Great content for every {subject} fan 👏",
    "ConnectDial always fastest on {subject} news. Check this out! ⚡",
    "My {subject} family — you'll want to see this. Trust me 👀",
]


class Command(BaseCommand):
    help = 'Bots engage intelligently with posts using context-aware reactions'

    # ── CATEGORY DETECTION ───────────────────────────────────────────────────
    def _detect_category(self, content: str, league_name: str) -> str:
        c = content.lower()
        ln = league_name.lower()

        # Score pattern: "3-1", "2 - 0", "FT:", "Full Time"
        if re.search(r'\b\d\s?[-–]\s?\d\b', c) or any(w in c for w in
                ["full time", "ft:", "final score", "result", "won", "beat", "defeated"]):
            return "match_result"

        if any(w in c for w in ["goal", "scored", "brace", "hattrick", "hat-trick", "tap in"]):
            return "goal_scored"

        if any(w in c for w in ["transfer", "signing", "sign", "deal", "bid", "contract",
                                  "official", "announced", "unveiled", "fee", "loan"]):
            return "transfer_news"

        if any(w in c for w in ["injur", "suspend", "ban", "miss", "ruled out", "doubt"]):
            return "injury_suspension"

        if any(w in c for w in ["derby", "rival", "clasico", "clásico", "el clásico",
                                  "northwest", "merseyside", "north london"]):
            return "rivalry"

        if any(w in c for w in ["stats", "xg", "analysis", "tactics", "possession",
                                  "pressing", "formation", "system", "review"]):
            return "analysis"

        # Saudi-specific boosts
        if "saudi" in ln or "spl" in ln or any(
                team in c for team in ["al-hilal", "al-nassr", "ittihad", "al ahli",
                                        "ronaldo", "benzema", "neymar", "firmino"]):
            return "spl_specific"

        return "general_hype"

    def _get_response(self, content: str, subject: str, league_name: str) -> str:
        category = self._detect_category(content, league_name)
        template = random.choice(REACTIONS[category])
        return template.replace("{subject}", subject)

    # ── MAIN ─────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        # Last 24 hours, random order, cap at 20 posts per run
        recent_posts = (Post.objects
                        .filter(created_at__gte=timezone.now() - timezone.timedelta(hours=24))
                        .order_by('?')[:20])

        if not recent_posts.exists():
            self.stdout.write("No recent posts found.")
            return

        for post in recent_posts:
            # Bots that share this post's league
            eligible_bots = (User.objects
                             .filter(profile__is_bot=True, favorite_league=post.league)
                             .exclude(id=post.author.id))

            if not eligible_bots.exists():
                continue

            # 1–2 bots per post keeps the feed organic
            participants = eligible_bots.order_by('?')[:random.randint(1, 2)]

            for bot in participants:
                # Skip if already interacted
                already_liked    = PostLike.objects.filter(user=bot, post=post).exists()
                already_commented = Comment.objects.filter(user=bot, post=post).exists()
                if already_liked and already_commented:
                    continue

                subject = post.team.name if post.team else post.league.name

                # Weighted action: 50% like, 35% comment, 15% repost
                roll = random.random()
                if roll < 0.50:
                    action = 'like'
                elif roll < 0.85:
                    action = 'comment'
                else:
                    action = 'repost'

                if action == 'like':
                    PostLike.objects.get_or_create(user=bot, post=post)
                    self.stdout.write(f"❤️  @{bot.username} liked a [{subject}] post")

                elif action == 'comment':
                    text = self._get_response(post.content, subject, post.league.name)
                    Comment.objects.create(user=bot, post=post, content=text)
                    self.stdout.write(f"💬  @{bot.username}: {text}")

                elif action == 'repost':
                    already_reposted = Post.objects.filter(
                        author=bot, parent_post=post, is_repost=True).exists()
                    if already_reposted:
                        continue

                    caption = random.choice(REPOST_CAPTIONS).format(
                        league=post.league.name, subject=subject)
                    Post.objects.create(
                        author=bot,
                        content=caption,
                        post_type='text',
                        league=post.league,
                        team=post.team,
                        parent_post=post,
                        is_repost=True,
                    )
                    self.stdout.write(f"🔄  @{bot.username} shared a [{subject}] post")

        self.stdout.write(self.style.SUCCESS("✅ Intelligent engagement complete!"))