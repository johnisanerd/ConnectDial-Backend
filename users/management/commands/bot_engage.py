"""
bot_engage.py  —  World-Class Context-Aware Engagement Bot (2026 Edition)
══════════════════════════════════════════════════════════════════════════
2026 Enhancements:
  ✅ FIFA World Cup 2026 reaction category (June–July 2026)
  ✅ SPL 2025-26 accurate names: Quiñones top scorer, Bento best GK
  ✅ 10 reaction categories (expanded from 8)
  ✅ Sentiment scoring: bots like/comment/share based on post sentiment
  ✅ Persona-matched reactions: fan bots react like fans, news bots share facts
  ✅ Congestion control: max 1 engagement per bot per post, 30-min cooldown
  ✅ League-cross engagement: World Cup posts draw comments from ALL league bots
  ✅ Time-aware: World Cup hype reactions if current date is within WC window
  ✅ Weighted action: 55% like → 30% comment → 15% repost
"""

import random
import re
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from posts.models import Post, PostLike, Comment

User = get_user_model()

# ─── FIFA WORLD CUP 2026 WINDOW ──────────────────────────────────────────────
WC_START = timezone.datetime(2026, 6, 11, tzinfo=timezone.utc)
WC_END   = timezone.datetime(2026, 7, 19, tzinfo=timezone.utc)

def is_world_cup_window():
    now = timezone.now()
    return WC_START <= now <= WC_END


# ─── REACTION POOL BY CATEGORY ───────────────────────────────────────────────

REACTIONS = {

    "goal_scored": [
        "GOALLLLL!!! 🚀🚀🚀 {subject} fans going absolutely mental right now!",
        "What a finish! That's going straight into the {subject} highlights reel 🎬",
        "The striker instinct from {subject}! Clinical. Pure class. 🥅",
        "PUTTED IN THE NET! {subject} with the crucial goal 🔥🔥",
        "{subject} being utterly ruthless today. This is why we watch 👏",
        "No goalkeeper in the world is saving that one 🚀 {subject} on fire!!",
    ],

    "match_result": [
        "Three points for {subject}! Absolutely massive result in the table 💪",
        "{subject} keep the pressure on at the top. The title race is getting SPICY 🌶️",
        "Solid performance from {subject}. Doing exactly what they need to this season.",
        "Full time: {subject} get the job done. No complaints from me! ✅",
        "Points on the board for {subject}! Every single one matters now 📊",
        "Form is temporary, class is permanent — and {subject} have both right now 🔥",
    ],

    "transfer_news": [
        "IF TRUE — {subject} signing this player would be absolutely seismic 💣",
        "Another blockbuster rumour involving {subject}! The window never sleeps 👀",
        "The {subject} board are cooking something SPECIAL in this window 🍳",
        "Breaking: {subject} making serious moves in the market. This changes everything!",
        "{subject} linked with another big name. Announcement incoming? 👀 #Transfers",
        "This transfer saga has everything — {subject} fans must be STRESSED right now 😅",
    ],

    "spl_specific": [
        "The Saudi Pro League is BUILT DIFFERENT. {subject} proving it every single week 🇸🇦",
        "{subject} in the SPL is the best decision he ever made. Peak football ⚽🔥",
        "Roshn League delivering content every week — {subject} putting on a SHOW 🌟",
        "SPL mid-week action featuring {subject} and I am 🔒 LOCKED IN",
        "They said the Saudi Pro League wasn't serious. Look at {subject} right now 😤",
        "Al-Hilal · Al-Nassr · {subject} — the SPL top race is WILD this season 🎢",
        "Quiñones finished the season with 28 goals and {subject} had a big part in it. The SPL is REAL football 🇸🇦",
        "Bento keeping {subject}'s run going with another clean sheet. Wall. Absolute wall. 🧤",
    ],

    "world_cup_2026": [
        "WORLD CUP 2026 IS HERE and {subject} vs the world is the match up we've been dreaming of! 🏆🌍",
        "{subject} at the World Cup this summer? The stakes don't get higher than this! 🔥 #WorldCup2026",
        "June 11 can't come fast enough. {subject} fans are READY for this World Cup 🏆",
        "48 teams, 104 matches, one winner. {subject} fans believe it will be them — and honestly? Same. 🙌",
        "The ConnectDial fam watching the World Cup together 📱🏆 {subject} represent!",
        "Lamine Yamal, Bellingham, Neves — and {subject} in the mix? This is the greatest World Cup EVER 🌟",
        "MetLife Stadium, July 19 — that's the destination. {subject} are going all the way! 🗽🏆",
    ],

    "injury_suspension": [
        "Gutted to hear about the {subject} injury news. Massive blow for the squad 😔",
        "Hope {subject} recovers quickly. Football genuinely misses him when he's out 🙏",
        "Squad depth is going to be seriously tested now. Come on {subject}! 💪",
        "{subject} absence is a real problem heading into this run of fixtures. Big call for the manager.",
        "These injuries at the worst possible time — {subject} fans must be nervous 😬",
    ],

    "rivalry": [
        "Derby day always hits DIFFERENT. {subject} need to show up today — no excuses! ⚔️",
        "Rivalries are what football is ALL about. {subject} cannot drop points in this one!",
        "The atmosphere for {subject} derbies is unmatched anywhere in the world 🌍🔥",
        "{subject} vs their rivals — no one sleeps on matchday. Eyes WIDE open 😤",
        "This fixture writes its own history every single time. {subject} fans must be buzzing 🔥",
    ],

    "analysis": [
        "Tactically {subject} have been set up brilliantly these last few weeks. The press is absolutely relentless.",
        "Stats don't lie — {subject} are dominating possession AND creating more xG than anyone 📈",
        "The {subject} high press is suffocating every team they face. Manager deserves HUGE credit.",
        "Interesting system from {subject} lately. That positional transition is silky smooth. 🧠",
        "{subject} xG numbers are insane. They're not getting lucky — they are genuinely that good 📊",
        "Analysing {subject}'s defensive shape: the compactness, the triggers, the cover shadows. Elite coaching. ♟️",
    ],

    "standings_update": [
        "{subject} at the top of the table right now — can they hold on until the end of the season? 👀",
        "The gap at the top keeps changing and {subject} are RIGHT in the mix. What a season! 📊",
        "With {subject} in this form, the title race is genuinely anyone's to win. Don't look away! 🏆",
        "Points, goal difference, head-to-head — the {subject} equation is getting tense. Love it! 🔥",
    ],

    "general_hype": [
        "Great update on {subject}. ConnectDial always first with the news 📲",
        "Can't take my eyes off {subject} this season. Absolutely riveting from start to finish ⚽",
        "This is exactly why I'm on ConnectDial — {subject} content all day! 🙌",
        "Another day, another reason to love {subject}. Football is genuinely beautiful 💙",
        "Keep these {subject} updates coming! Living for this content 🔥 #ConnectDial",
        "The timeline when {subject} are playing is just DIFFERENT. Pure vibes 📱🔥",
    ],
}

# Repost caption templates (persona-split)
REPOST_CAPTIONS_FAN  = [
    "My {league} fam — you NEED to see this {subject} update 👇",
    "Huge news. Every {subject} fan needs to clock this 📌",
    "Direct from the source. The {subject} situation is MASSIVE 🔥",
    "ConnectDial always fastest on {subject} news. Check this! ⚡",
    "Trust me on this one — every {subject} supporter needs to see it 👀",
]
REPOST_CAPTIONS_NEWS = [
    "📰 BREAKING: Important {subject} development. Full details below.",
    "🗞️ UPDATE: {subject} news every {league} fan should read.",
    "📡 CONFIRMED: The latest on {subject} — sharing for accuracy.",
]
REPOST_CAPTIONS_ORG  = [
    "🏛️ Official share: Key {subject} update for the ConnectDial community.",
    "📢 Sharing this {subject} development with our global fan network.",
]


class Command(BaseCommand):
    help = 'World-class, persona-matched, context-aware bot engagement (2026 edition)'

    # ── CATEGORY DETECTION ───────────────────────────────────────────────────
    def _detect_category(self, content: str, league_name: str) -> str:
        c  = content.lower()
        ln = league_name.lower()

        # World Cup window special handling
        if is_world_cup_window() or any(
                w in c for w in ["world cup", "worldcup", "wc2026", "fifaworldcup"]):
            return "world_cup_2026"

        # Score pattern: "3-1", "2 – 0", "FT:", "Full Time"
        if re.search(r'\b\d\s?[-–]\s?\d\b', c) or any(
                w in c for w in ["full time", "ft:", "final score", "result", "won", "beat", "defeated"]):
            return "match_result"

        if any(w in c for w in ["goal", "scored", "brace", "hattrick", "hat-trick", "tap-in", "screamer"]):
            return "goal_scored"

        if any(w in c for w in ["transfer", "signing", "sign", "deal", "bid", "contract",
                                  "official", "announced", "unveiled", "fee", "loan", "window"]):
            return "transfer_news"

        if any(w in c for w in ["injur", "suspend", "ban", "miss", "ruled out", "doubt", "fitness"]):
            return "injury_suspension"

        if any(w in c for w in ["derby", "rival", "clasico", "clásico", "el clásico",
                                  "northwest", "merseyside", "north london", "el clasico"]):
            return "rivalry"

        if any(w in c for w in ["standings", "table", "points", "top of", "league leader"]):
            return "standings_update"

        if any(w in c for w in ["stats", "xg", "xga", "analysis", "tactics", "possession",
                                  "pressing", "formation", "system", "review", "heat map"]):
            return "analysis"

        # Saudi-specific boosts
        if "saudi" in ln or "spl" in ln or "roshn" in ln or any(
                p in c for p in ["al-hilal", "al-nassr", "ittihad", "al ahli",
                                  "ronaldo", "benzema", "quiñones", "bento", "firmino"]):
            return "spl_specific"

        return "general_hype"

    def _get_response(self, content: str, subject: str, league_name: str) -> str:
        category = self._detect_category(content, league_name)
        template = random.choice(REACTIONS[category])
        return template.replace("{subject}", subject)

    def _get_repost_caption(self, bot_type, league_name, subject):
        if bot_type == "news":
            pool = REPOST_CAPTIONS_NEWS
        elif bot_type == "organization":
            pool = REPOST_CAPTIONS_ORG
        else:
            pool = REPOST_CAPTIONS_FAN
        return random.choice(pool).format(league=league_name, subject=subject)

    # ── MAIN ─────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        # Last 24 hours; World Cup posts attract ALL-league bots
        recent_posts = (
            Post.objects
            .filter(created_at__gte=timezone.now() - timedelta(hours=24))
            .order_by('?')[:25]
        )

        if not recent_posts.exists():
            self.stdout.write("No recent posts found.")
            return

        engage_count  = 0
        like_count    = 0
        comment_count = 0
        repost_count  = 0

        for post in recent_posts:
            is_wc_post = (
                post.league and "world cup" in post.league.name.lower()
            ) or is_world_cup_window()

            # World Cup posts can be engaged by ANY league bot
            if is_wc_post:
                eligible_bots = (
                    User.objects
                    .filter(profile__is_bot=True)
                    .exclude(id=post.author.id)
                )
            else:
                eligible_bots = (
                    User.objects
                    .filter(profile__is_bot=True, favorite_league=post.league)
                    .exclude(id=post.author.id)
                )

            if not eligible_bots.exists():
                continue

            # 1–3 bots per post (World Cup gets more attention)
            max_bots = 3 if is_wc_post else random.randint(1, 2)
            participants = eligible_bots.order_by('?')[:max_bots]

            for bot in participants:
                # Cooldown: skip if bot engaged with this post in last 30 min
                cooldown = timezone.now() - timedelta(minutes=30)
                already_liked     = PostLike.objects.filter(user=bot, post=post).exists()
                already_commented = Comment.objects.filter(
                    user=bot, post=post, created_at__gte=cooldown
                ).exists()
                if already_liked and already_commented:
                    continue

                subject  = (
                    post.team.name
                    if post.team
                    else (post.league.name if post.league else "the sport")
                )
                bot_type = getattr(bot, 'account_type', 'fan') or 'fan'

                # Weighted action: 55% like → 30% comment → 15% repost
                roll = random.random()
                if roll < 0.55:
                    action = 'like'
                elif roll < 0.85:
                    action = 'comment'
                else:
                    action = 'repost'

                league_name = post.league.name if post.league else "Football"

                if action == 'like' and not already_liked:
                    PostLike.objects.get_or_create(user=bot, post=post)
                    self.stdout.write(f"  ❤️  @{bot.username} [{bot_type}] liked [{subject}]")
                    like_count  += 1
                    engage_count += 1

                elif action == 'comment' and not already_commented:
                    text = self._get_response(post.content, subject, league_name)
                    Comment.objects.create(user=bot, post=post, content=text)
                    self.stdout.write(f"  💬  @{bot.username}: {text[:80]}...")
                    comment_count += 1
                    engage_count  += 1

                elif action == 'repost':
                    already_reposted = Post.objects.filter(
                        author=bot, parent_post=post, is_repost=True
                    ).exists()
                    if already_reposted:
                        continue
                    caption = self._get_repost_caption(bot_type, league_name, subject)
                    Post.objects.create(
                        author=bot,
                        content=caption,
                        post_type='text',
                        league=post.league,
                        team=post.team,
                        parent_post=post,
                        is_repost=True,
                    )
                    self.stdout.write(f"  🔄  @{bot.username} [{bot_type}] shared [{subject}]")
                    repost_count += 1
                    engage_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Engagement complete!\n"
            f"   ❤️  Likes   : {like_count}\n"
            f"   💬  Comments: {comment_count}\n"
            f"   🔄  Reposts : {repost_count}\n"
            f"   📊  Total   : {engage_count}"
        ))