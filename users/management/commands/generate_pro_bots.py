"""
generate_pro_bots.py  —  Official News & Organisation Bot Generator (2026 Edition)
══════════════════════════════════════════════════════════════════════════════════
2026 Enhancements:
  ✅ FIFA World Cup 2026 dedicated media/org brands
  ✅ SPL 2025-26 Roshn League accurate brand names
  ✅ Pixabay API for studio/organisation imagery
  ✅ Verified bios referencing actual 2026 tournaments and stories
  ✅ Duplicate brand name prevention
  ✅ Badge assignment: 'official' for news, 'verified' for orgs
"""

import random
import time
import requests
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from users.models import Profile
from leagues.models import League

User = get_user_model()

PEXELS_API_KEY  = "HNdRlaon0CTc9qoCrFUYUNrnrHV6wpyetmhozjBUhpZ9tnVPPvZIBWO5"
PIXABAY_API_KEY = "YOUR_PIXABAY_KEY_HERE"

NEWS_PREFIXES = ["Daily", "Global", "Sports", "Fanatic", "Inside", "The", "Rapid", "Flash",
                  "Elite", "Premier", "Ultra", "Arena", "Pitch", "Bleacher", "TransferRoom",
                  "MatchDay", "TacticsHQ", "LiveScore", "World"]
NEWS_SUFFIXES = ["News", "Updates", "Report", "Central", "Hub", "Network", "Wire", "Desk",
                  "Pulse", "Feed", "Live", "Zone", "Insider", "Today", "HQ", "Digest", "Tracker"]
ORG_TYPES     = ["Foundation", "Academy", "Agency", "Group", "Sports Club",
                  "Association", "Institute", "Media", "Supporters Club", "Ultras Official",
                  "Fanzone", "Trust", "Community", "Hub"]

# Pre-built branded names per league — these feel the most authentic
LEAGUE_BRANDS = {
    "saudi pro league": {
        "news": ["Roshn League Pulse", "Al-Dawri Insider", "SPL Wire", "Gulf Football Report",
                  "Saudi Sports Desk", "Roshn League HQ", "SPL Transfer Tracker"],
        "org":  ["Saudi Football Foundation", "SPL Supporters HQ", "Gulf Football Academy",
                  "Roshn League Community", "Al-Dawri Fanzone"],
    },
    "premier league": {
        "news": ["EPL Central", "Premier Wire", "TopFlight Report", "Matchday Live",
                  "Three Lions Report", "PL Insider", "Premier League Tracker"],
        "org":  ["PL Supporters Trust", "Three Lions Academy", "Premier Football Group",
                  "English Football Community"],
    },
    "champions league": {
        "news": ["UCL Insider", "European Nights Report", "Champions Wire", "UCL Pulse",
                  "European Football Desk"],
        "org":  ["UCL Supporters Club", "European Football Academy", "Champions League Hub"],
    },
    "la liga": {
        "news": ["LaLiga Wire", "ElClasico Insider", "Spanish Football Report", "LaLiga Pulse"],
        "org":  ["LaLiga Supporters Trust", "Spanish Football Academy", "Iberian Football Hub"],
    },
    "serie a": {
        "news": ["Calcio Insider", "Serie A Wire", "Italian Football Report", "Serie A Central"],
        "org":  ["Calcio Supporters Club", "Italian Football Academy", "Serie A Community"],
    },
    "bundesliga": {
        "news": ["Bundesliga Wire", "German Football Insider", "BL1 Report", "Bundesliga Pulse"],
        "org":  ["Bundesliga Supporters Trust", "German Football Academy"],
    },
    "nba": {
        "news": ["NBA Wire", "Hoops Insider", "Basketball Report", "NBA Central", "Court Report"],
        "org":  ["NBA Fans Foundation", "Hoops Academy", "Basketball Community Hub"],
    },
    "mls": {
        "news": ["MLS Insider", "American Soccer Report", "MLS Wire", "US Soccer Desk"],
        "org":  ["MLS Supporters Trust", "American Soccer Academy", "US Football Hub"],
    },
    "fifa world cup": {
        "news": ["WC2026 Insider", "World Cup Wire", "FIFA Report 2026", "WC2026 Pulse",
                  "World Cup Desk", "FIFA 2026 Tracker"],
        "org":  ["World Cup Supporters Club", "FIFA 2026 Community", "WC2026 Fanzone",
                  "Global Football Foundation"],
    },
}

# 2026-accurate news bio templates
NEWS_BIOS_2026 = {
    "saudi pro league": [
        "SPL news 24/7. Roshn League 2025-26 coverage — Quiñones 28 goals, Bento 13 clean sheets ✅ #ConnectDial",
        "Official Saudi Pro League news source. Al-Nassr · Al-Hilal · All clubs. Verified updates ✅",
        "Your fastest source for Roshn Saudi League news. Transfers, results, analysis 🇸🇦 #ConnectDial",
    ],
    "premier league": [
        "Breaking Premier League news around the clock. Transfers · Match reports · Analysis ✅ #PL",
        "Your fastest EPL source on ConnectDial. Verified football journalism 🏴󠁧󠁢󠁥󠁮󠁧󠁿 #PremierLeague",
    ],
    "fifa world cup": [
        "FIFA World Cup 2026 coverage. USA / Mexico / Canada — 48 nations, 104 matches. Verified ✅ #WC2026",
        "Your World Cup 2026 news hub. June 11 – July 19. Every goal, every story 🏆 #ConnectDial",
        "Official-grade World Cup 2026 coverage. Groups, squads, results. Stay with us all summer ⚽",
    ],
    "generic": [
        "Breaking {league} news 24/7. Verified facts only ✅ #ConnectDial",
        "Your fastest source for {league} updates. Transfers · Results · Deep analysis.",
    ],
}

ORG_BIOS_2026 = {
    "saudi pro league": [
        "Official Saudi Pro League supporter community. Supporting the Roshn League globally 🇸🇦 ✅",
        "SPL supporter network. Connecting Gulf football fans worldwide on ConnectDial 🌍",
    ],
    "fifa world cup": [
        "FIFA World Cup 2026 official fan community. Celebrating football from 48 nations 🏆🌍 ✅",
        "World Cup 2026 supporter network — USA, Mexico, Canada. Everyone is welcome 🌎 #WC2026",
    ],
    "generic": [
        "Supporting the growth of {league} worldwide. Official Account ✅ #ConnectDial",
        "Connecting {league} fans globally. Join our community 🌍",
    ],
}


class Command(BaseCommand):
    help = 'Generates 2026-accurate Official News and Organisation bots with league-aware branding'

    def add_arguments(self, parser):
        parser.add_argument('total', type=int, help='Number of Pro bots to create')
        parser.add_argument(
            '--league', type=str, default=None,
            help='Target specific league (optional)'
        )

    def _branded_name(self, acc_type, league):
        league_lower = league.name.lower()
        brands = LEAGUE_BRANDS.get(league_lower, {})
        pool   = brands.get('news' if acc_type == 'news' else 'org', [])
        if pool:
            return random.choice(pool)
        # Generated fallback
        if acc_type == 'news':
            return f"{random.choice(NEWS_PREFIXES)} {league.name} {random.choice(NEWS_SUFFIXES)}"
        return f"{league.name} {random.choice(ORG_TYPES)}"

    def _build_bio(self, acc_type, league):
        ln = league.name.lower()
        if acc_type == 'news':
            pool = NEWS_BIOS_2026.get(ln, NEWS_BIOS_2026["generic"])
        else:
            pool = ORG_BIOS_2026.get(ln, ORG_BIOS_2026["generic"])
        return random.choice(pool).format(league=league.name)

    def _fetch_image(self, search_term, user_id):
        headers = {'User-Agent': 'Mozilla/5.0'}
        # Try Pixabay
        if PIXABAY_API_KEY != "YOUR_PIXABAY_KEY_HERE":
            try:
                url = (
                    f"https://pixabay.com/api/"
                    f"?key={PIXABAY_API_KEY}&q={search_term.replace(' ', '+')}"
                    f"&image_type=photo&per_page=10&safesearch=true"
                )
                r    = requests.get(url, timeout=8).json()
                hits = r.get("hits", [])
                if hits:
                    img_url = random.choice(hits[:5]).get("webformatURL")
                    if img_url:
                        res = requests.get(img_url, headers=headers, timeout=12)
                        if res.status_code == 200:
                            return res.content
            except Exception:
                pass
        # Pexels fallback
        try:
            pexels_url = (
                f"https://api.pexels.com/v1/search"
                f"?query={search_term}&per_page=10"
            )
            ph  = {"Authorization": PEXELS_API_KEY}
            r   = requests.get(pexels_url, headers=ph, timeout=8).json()
            photos = r.get("photos", [])
            if photos:
                img_url = random.choice(photos[:5]).get("src", {}).get("medium")
                if img_url:
                    res = requests.get(img_url, headers=headers, timeout=12)
                    if res.status_code == 200:
                        return res.content
        except Exception:
            pass
        return None

    def handle(self, *args, **options):
        total         = options['total']
        league_filter = options.get('league')

        leagues = list(League.objects.all())
        if league_filter:
            leagues = [l for l in leagues if league_filter.lower() in l.name.lower()]
        if not leagues:
            self.stdout.write(self.style.ERROR('❌ No leagues found in DB.'))
            return

        used_names = set()
        created    = 0
        self.stdout.write(f"🚀 Deploying {total} Professional Accounts...")

        for i in range(total):
            acc_type   = 'news' if i % 2 == 0 else 'organization'
            badge      = 'official' if acc_type == 'news' else 'verified'
            fav_league = random.choice(leagues)
            suffix     = random.randint(100, 999)

            # Get a unique brand name
            for _ in range(5):
                display_name = self._branded_name(acc_type, fav_league)
                if display_name not in used_names:
                    used_names.add(display_name)
                    break
            username = display_name.replace(" ", "_").lower().replace("'", "") + f"_{suffix}"

            bio = self._build_bio(acc_type, fav_league)
            search_term = (
                "news studio broadcast journalism sports"
                if acc_type == 'news'
                else "stadium sports office organization management"
            )

            try:
                if User.objects.filter(username=username).exists():
                    username += f"_{random.randint(10, 99)}"

                user = User.objects.create(
                    username=username,
                    email=f"pro_{suffix}_{i}@connectdial.com",
                    favorite_league=fav_league,
                    account_type=acc_type,
                    fan_badge=badge,
                )
                user.set_password('connect_pro_2026')
                user.save()

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.display_name = display_name
                profile.is_bot       = True
                profile.bio          = bio
                profile.save()

                self.stdout.write(
                    f"  [{i+1}/{total}] {badge.upper()} → {display_name} | {fav_league.name}"
                )

                img_data = self._fetch_image(search_term, user.id)
                if img_data:
                    profile.profile_image.save(
                        f"pro_{user.id}.jpg", ContentFile(img_data), save=True
                    )

                created += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {username}: {e}"))

            time.sleep(0.8)

        self.stdout.write(self.style.SUCCESS(
            f'✅ {created}/{total} Professional bots deployed!'
        ))