"""
upgrade_junk_posts.py  —  Legacy Junk-Post Repair
═══════════════════════════════════════════════════
The generic "Check this out! #PremierLeague" posts in your feed were created by
an OLD seeding script (not by bot_post.py / bot_engage.py — those produce rich
content). Those rows are still in the DB. This command finds them and either:

  • rewrites them into rich, varied, league-accurate content  (default), or
  • deletes them entirely                                       (--delete)

Place this file at:  <app>/management/commands/upgrade_junk_posts.py
(use the same app that holds bot_post.py)

Usage:
  python manage.py upgrade_junk_posts --dry-run            # preview, change nothing
  python manage.py upgrade_junk_posts                      # rewrite junk → rich content
  python manage.py upgrade_junk_posts --delete             # delete junk instead
  python manage.py upgrade_junk_posts --league "Premier League"
"""

import random
import re
from django.core.management.base import BaseCommand
from posts.models import Post

# ─────────────────────────────────────────────────────────────────────────────
# WHAT COUNTS AS "JUNK"
# A bot post is junk if its content is generic/empty/too-short to be meaningful.
# ─────────────────────────────────────────────────────────────────────────────
JUNK_PATTERNS = [
    re.compile(r'^\s*check\s+this\s+out', re.IGNORECASE),
    re.compile(r'^\s*#\w+\s*$'),                 # nothing but a hashtag
    re.compile(r'^\s*(post|update|new|content)\s*[!.]*\s*$', re.IGNORECASE),
]
JUNK_MIN_LENGTH = 25   # bare "Check this out! #PL" is ~30 chars; strip tags first


def _strip_tags(text):
    return re.sub(r'#\w+', '', text or '').strip()


def is_junk(content):
    if not content or not content.strip():
        return True
    for pat in JUNK_PATTERNS:
        if pat.match(content):
            return True
    # Generic if there's almost no real text once hashtags are removed
    if len(_strip_tags(content)) < JUNK_MIN_LENGTH:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# RICH CONTENT — combinatorial builder + verified static lines
# The builder assembles opener + subject + take + CTA + tags for thousands of
# unique combinations, so bots never look repetitive even with APIs off.
# ─────────────────────────────────────────────────────────────────────────────

LEAGUE_TAGS = {
    "premier league":   ["PremierLeague", "EPL", "PL"],
    "la liga":          ["LaLiga", "PrimeraDivision"],
    "serie a":          ["SerieA", "Calcio"],
    "bundesliga":       ["Bundesliga", "BL1"],
    "ligue 1":          ["Ligue1", "FrenchFootball"],
    "champions league": ["UCL", "ChampionsLeague"],
    "saudi pro league": ["SPL", "RoshnLeague", "SaudiProLeague"],
    "nba":              ["NBA", "Basketball"],
    "mls":              ["MLS", "MLSSoccer"],
    "fifa world cup":   ["WorldCup2026", "WC2026", "FIFAWorldCup2026"],
}

# Verified, season-accurate fan takes (reused from your own bot_post.py pools)
STATIC = {
    "saudi pro league": [
        "Julián Quiñones finished the 2025-26 Roshn League as top scorer with 28 goals — and made it look easy. The man is CLINICAL. 🇸🇦",
        "Al-Nassr's 16-match winning run and Al-Hilal's 29-match unbeaten run in one season. The SPL is producing genuine world-level consistency. 📊",
        "Bento with 13 clean sheets this season — an absolute wall. Best keeper in the Roshn League, no debate. 🧤",
        "Al-Nassr vs Al-Hilal pulled 53,883 fans in September. Bigger than most weekend fixtures in Europe. The SPL is a movement, not a gimmick. 🔥",
    ],
    "premier league": [
        "The top-four race is going to the last day again. This is exactly why the Premier League is the most watched league on earth. 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "Pressing intensity across the Premier League this season is at an all-time high. Every side wins the ball higher up the pitch now. 🧠",
        "Every Premier League fixture feels like a cup final. That's the standard, and it keeps delivering weekend after weekend. ⚽",
    ],
    "champions league": [
        "Nothing in club football compares to a Champions League knockout night. The anthem hits and the heart rate goes to 150. ⭐",
        "xG doesn't lie — the best teams in this season's UCL are creating chances, not parking the bus. Genuinely world-class football. 📊",
    ],
    "la liga": [
        "La Liga's positional play and pressing triggers are a tactics masterclass. You learn football just by watching closely. 🇪🇸",
        "El Clásico season is *always* in La Liga. The tactical battles are elite. 🧠",
    ],
    "serie a": [
        "The catenaccio label is officially outdated — Serie A is all high press and verticality now. Italian football has evolved beautifully. 🇮🇹",
        "Serie A title races are chess on grass. Some of the most carefully built football anywhere. ♟️",
    ],
    "bundesliga": [
        "3+ goals per game average, highest press intensity in Europe, generational youth talent. The Bundesliga is built right. 🇩🇪",
        "The next Bellingham and the next Haaland will come through the Bundesliga. No academy system matches it right now. 🌟",
    ],
    "nba": [
        "The NBA has never had this many 30-points-per-game scorers at the same time. The talent depth is staggering. 🏀",
        "Conference finals will sort the pretenders from the contenders. The basketball has been elite all season. 🏆",
    ],
    "mls": [
        "With the World Cup right here in North America, US soccer culture is at an all-time high. MLS is the biggest beneficiary. 🇺🇸",
        "62 million soccer fans in the USA — fourth-largest fanbase globally. The World Cup effect is real. 🌎",
    ],
    "fifa world cup": [
        "World Cup 2026: 48 nations, 104 matches, 3 host countries. The biggest tournament in history kicks off June 11. 🏆",
        "Final at MetLife Stadium on July 19. The whole planet stops for 90 minutes. Are you ready? 🌍",
        "48 teams, one trophy. The young talent at this World Cup is the most exciting we've ever had. 🌟",
    ],
    "generic": [
        "Sport doesn't take a day off and neither do we. Locked in for the latest from leagues across the globe. 🌍",
        "Football in 2026 is having its greatest year ever — from the SPL to the World Cup. What a time to be a fan. ⚽",
    ],
}

# Combinatorial fragments for endless variety, with {subject} = team or league
OPENERS = [
    "Hot take:", "Real talk —", "Say it louder:", "Genuine question for the timeline:",
    "Stat of the day:", "Matchday mood:", "Unpopular opinion?", "Calling it now —",
    "This needs saying:", "Quietly brilliant:",
]
TAKES = [
    "{subject} have been the story of the season and it's not close.",
    "the form {subject} are in right now is genuinely special to watch.",
    "{subject} fans have every reason to be buzzing this week.",
    "you can't talk about {league} this season without mentioning {subject}.",
    "{subject} are doing the unglamorous things brilliantly — and it's working.",
    "the {subject} project is finally clicking, and the table shows it.",
    "{subject} on their day can beat anyone in {league}. Anyone.",
    "watching {subject} is a reminder of why we fell for this sport.",
]
CTAS = [
    "Who's with me? 👇", "Tell me I'm wrong. 😤", "Drop your take below. 💬",
    "Agree or disagree? 👀", "Save this and check back in May. 📌",
    "The timeline is going to have opinions on this one. 🔥", "",
]


def _build_dynamic(subject, league):
    opener = random.choice(OPENERS)
    take = random.choice(TAKES).format(subject=subject, league=league)
    cta = random.choice(CTAS)
    text = f"{opener} {take}"
    if cta:
        text += f" {cta}"
    return text.strip()


def _hashtags(league_name):
    base = ["ConnectDial", league_name.replace(" ", "")]
    extra = LEAGUE_TAGS.get(league_name.lower(), [])
    chosen = base + random.sample(extra, min(2, len(extra)))
    return " ".join(f"#{t}" for t in dict.fromkeys(chosen))


def build_content(post, used_by_author):
    """Produce a rich, non-repeating caption for this post."""
    league_name = post.league.name if post.league else "Football"
    subject = post.team.name if post.team else league_name

    for _ in range(8):  # try a few times to avoid repeating per author
        if random.random() < 0.55:
            body = _build_dynamic(subject, league_name)
        else:
            pool = STATIC.get(league_name.lower(), STATIC["generic"])
            body = random.choice(pool)
        full = f"{body} {_hashtags(league_name)}"
        if full not in used_by_author:
            used_by_author.add(full)
            return full
    return full  # accept a repeat only if we genuinely ran out


class Command(BaseCommand):
    help = "Find legacy generic bot posts and rewrite them into rich content (or delete them)."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Preview only; change nothing.')
        parser.add_argument('--delete', action='store_true',
                            help='Delete junk posts instead of rewriting them.')
        parser.add_argument('--league', type=str, default=None,
                            help='Restrict to one league (optional).')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delete  = options['delete']
        league  = options.get('league')

        qs = Post.objects.filter(author__profile__is_bot=True)
        if league:
            qs = qs.filter(league__name__icontains=league)

        junk = [p for p in qs if is_junk(p.content)]
        if not junk:
            self.stdout.write(self.style.SUCCESS("✨ No junk bot posts found. Feed is clean."))
            return

        verb = "DELETE" if delete else "REWRITE"
        self.stdout.write(
            f"{'[DRY RUN] ' if dry_run else ''}Found {len(junk)} junk bot post(s) to {verb}."
        )

        used = {}          # author_id -> set of captions already assigned
        changed = 0

        for post in junk:
            if delete:
                self.stdout.write(f"  🗑️  post {post.id}: {post.content[:50]!r}")
                if not dry_run:
                    post.delete()
                changed += 1
                continue

            author_set = used.setdefault(post.author_id, set())
            new_content = build_content(post, author_set)
            self.stdout.write(
                f"  ✏️  post {post.id}: {post.content[:30]!r} → {new_content[:60]!r}"
            )
            if not dry_run:
                post.content = new_content
                if post.post_type == 'text' or not post.post_type:
                    post.post_type = 'text'
                post.save(update_fields=['content'])
            changed += 1

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY RUN] ' if dry_run else ''}✅ {verb.title()}d {changed} post(s)."
        ))