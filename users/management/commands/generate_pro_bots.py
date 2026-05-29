"""
generate_pro_bots.py  —  Official News & Organisation Bot Generator (Apify Edition)
═════════════════════════════════════════════════════════════════════════════════════
Creates two of the three account types:
  • news         → media brands, journalists, sports desks  (badge: official)
  • organization → clubs, fan trusts, supporter groups       (badge: verified)
  (fans are created separately by generate_bots.py)

Image strategy — 3-source cascade, Apify first:
  1. Apify Google Images  → most varied, never the same generic stock shot
  2. Pexels               → reliable fallback
  3. Pixabay              → last resort

Each type gets a role-appropriate image search:
  news  → "sports journalist broadcast studio" / "sports news presenter"
  org   → "football club badge trophy" / "sports stadium exterior crowd"

Usage:
  python manage.py generate_pro_bots 20
  python manage.py generate_pro_bots 10 --type news --league "Premier League"
  python manage.py generate_pro_bots 10 --type organization
"""

import os
import random
import time
import requests
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from users.models import Profile
from leagues.models import League

User = get_user_model()

# ─── KEYS — all via environment ──────────────────────────────────────────────
APIFY_TOKEN    = os.environ.get("APIFY_TOKEN", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")

# ─── BRANDED NAMES ───────────────────────────────────────────────────────────
NEWS_PREFIXES = ["Daily", "Global", "Sports", "Inside", "The", "Rapid", "Flash",
                 "Elite", "Premier", "Ultra", "Arena", "Pitch", "Bleacher",
                 "TransferRoom", "MatchDay", "TacticsHQ", "LiveScore", "World"]
NEWS_SUFFIXES = ["News", "Updates", "Report", "Central", "Hub", "Network", "Wire",
                 "Desk", "Pulse", "Feed", "Live", "Zone", "Insider", "HQ",
                 "Digest", "Tracker", "Alert", "Today"]
ORG_TYPES     = ["FC", "Sports Club", "Supporters Club", "Ultras", "Fanzone",
                 "Trust", "Community", "Foundation", "Academy", "Association",
                 "Supporters Trust", "Fan Hub", "Barra Brava", "End"]

LEAGUE_BRANDS = {
    "saudi pro league": {
        "news": ["Roshn League Pulse", "Al-Dawri Insider", "SPL Wire",
                 "Gulf Football Report", "Saudi Sports Desk", "Roshn League HQ",
                 "SPL Transfer Tracker", "Roshn Match Centre"],
        "org":  ["Saudi Football Foundation", "SPL Supporters HQ",
                 "Gulf Football Academy", "Roshn League Community",
                 "Al-Dawri Fanzone", "SPL Ultra Network"],
    },
    "premier league": {
        "news": ["EPL Central", "Premier Wire", "TopFlight Report", "Matchday Live",
                 "Three Lions Report", "PL Insider", "Premier League Tracker",
                 "The Kop Report", "North Stand Wire"],
        "org":  ["PL Supporters Trust", "Three Lions Academy",
                 "Premier Football Group", "English Football Community",
                 "Terrace Talk HQ", "Kop Trust"],
    },
    "champions league": {
        "news": ["UCL Insider", "European Nights Report", "Champions Wire",
                 "UCL Pulse", "European Football Desk", "UCL Match Centre"],
        "org":  ["UCL Supporters Club", "European Football Academy",
                 "Champions League Hub", "Ultras Europe Network"],
    },
    "la liga": {
        "news": ["LaLiga Wire", "ElClasico Insider", "Spanish Football Report",
                 "LaLiga Pulse", "Bernabéu Report"],
        "org":  ["LaLiga Supporters Trust", "Spanish Football Academy",
                 "Iberian Football Hub", "Grada Norte Community"],
    },
    "serie a": {
        "news": ["Calcio Insider", "Serie A Wire", "Italian Football Report",
                 "Serie A Central", "Curva Sud Report"],
        "org":  ["Calcio Supporters Club", "Italian Football Academy",
                 "Serie A Community", "Ultras Italia Network"],
    },
    "bundesliga": {
        "news": ["Bundesliga Wire", "German Football Insider",
                 "BL1 Report", "Bundesliga Pulse", "Südtribüne Report"],
        "org":  ["Bundesliga Supporters Trust", "German Football Academy",
                 "Yellow Wall Community", "Fanblock Deutschland"],
    },
    "nba": {
        "news": ["NBA Wire", "Hoops Insider", "Basketball Report",
                 "NBA Central", "Court Report", "Rim Rockers News"],
        "org":  ["NBA Fans Foundation", "Hoops Academy",
                 "Basketball Community Hub", "Hardwood Trust"],
    },
    "mls": {
        "news": ["MLS Insider", "American Soccer Report", "MLS Wire",
                 "US Soccer Desk", "Supporters Shield Report"],
        "org":  ["MLS Supporters Trust", "American Soccer Academy",
                 "US Football Hub", "Capo Section Network"],
    },
    "fifa world cup": {
        "news": ["WC2026 Insider", "World Cup Wire", "FIFA Report 2026",
                 "WC2026 Pulse", "World Cup Desk", "FIFA 2026 Tracker"],
        "org":  ["World Cup Supporters Club", "FIFA 2026 Community",
                 "WC2026 Fanzone", "Global Football Foundation"],
    },
    "ligue 1": {
        "news": ["Ligue 1 Wire", "French Football Insider", "PSG Report",
                 "Ligue 1 Central", "Virage Nord Report"],
        "org":  ["Ligue 1 Supporters Trust", "French Football Academy",
                 "Kop de Boulogne Community", "Ultras France Network"],
    },
}

# ─── BIOS — distinct voice per type ──────────────────────────────────────────
NEWS_BIOS = {
    "saudi pro league": [
        "SPL news 24/7. Roshn League 2025-26 — Quiñones 28 goals, Bento 13 clean sheets ✅ #ConnectDial",
        "Official Saudi Pro League news source. Al-Nassr · Al-Hilal · All 18 clubs ✅",
        "Fastest Roshn Saudi League news: transfers, results, analysis 🇸🇦 #ConnectDial",
        "Breaking SPL news the moment it happens. Verified media account ✅ #RoshnLeague",
    ],
    "premier league": [
        "Breaking Premier League news around the clock. Transfers · Results · Analysis ✅ #PL",
        "Your fastest EPL source on ConnectDial. Verified journalism 🏴󠁧󠁢󠁥󠁮󠁧󠁿 #PremierLeague",
        "PL transfers, results and breaking news. Trusted by fans since day one ✅ #ConnectDial",
        "Everything Premier League — squad news, tactics, match reports ✅ #EPL",
    ],
    "champions league": [
        "UEFA Champions League coverage 24/7. Every result, verified ✅ #UCL #ConnectDial",
        "Your fastest UCL source. Knockout nights covered live ⭐ #ChampionsLeague",
        "Breaking Champions League news — squad updates, tactical analysis, results ✅ #UCL",
    ],
    "la liga": [
        "La Liga news 24/7 — Mbappé, Yamal, Raphinha. Every story verified ✅ #LaLiga",
        "Your fastest Spanish football source on ConnectDial 🇪🇸 #LaLiga #ConnectDial",
        "El Clásico · Transfers · Tactics. La Liga coverage you can trust ✅ #LaLiga",
    ],
    "serie a": [
        "Serie A news 24/7. Inter champions, Lautaro 16 goals. Verified ✅ #SerieA #ConnectDial",
        "Italian football coverage — results, transfers, tactical breakdowns ✅ #Calcio",
        "Your fastest Serie A source. No clickbait, just facts ✅ #SerieA #ConnectDial",
    ],
    "bundesliga": [
        "Bundesliga news 24/7. Kane 33 goals. Bayern dominant. Verified ✅ #Bundesliga",
        "German football coverage — results, transfers, youth news ✅ #Bundesliga #ConnectDial",
        "Your fastest Bundesliga source on ConnectDial 🇩🇪 Verified ✅ #BL1",
    ],
    "nba": [
        "NBA news 24/7 — scores, trades, analysis. Verified sports media ✅ #NBA #ConnectDial",
        "Breaking basketball news. OKC · Spurs · Knicks · Every team covered ✅ #NBA",
        "Your fastest NBA source on ConnectDial. Playoffs coverage live ✅ #Basketball",
    ],
    "mls": [
        "MLS news and World Cup 2026 coverage. American soccer's fastest source ✅ #MLS",
        "Major League Soccer — results, transfers, World Cup buildup ✅ #MLS #ConnectDial",
    ],
    "fifa world cup": [
        "FIFA World Cup 2026 coverage. 48 nations, 104 matches. Verified ✅ #WC2026",
        "Your World Cup 2026 news hub. June 11 – July 19 🏆 #ConnectDial",
        "Official-grade World Cup 2026 coverage. Groups · Squads · Results ✅ #FIFA2026",
    ],
    "generic": [
        "Breaking {league} news 24/7. Verified facts only ✅ #ConnectDial",
        "Your fastest source for {league} updates. Transfers · Results · Analysis ✅",
        "{league} media on ConnectDial. Verified official news account ✅",
    ],
}

ORGANIZATION_BIOS = {
    "saudi pro league": [
        "Official SPL supporter community. Roshn League fans worldwide 🇸🇦 ✅ #ConnectDial",
        "Saudi Pro League fan network. Al-Nassr · Al-Hilal · Every club 🌍 ✅",
        "Connecting Gulf football fans across the globe. SPL community ✅ #RoshnLeague",
        "Official Roshn League fan organisation on ConnectDial 🇸🇦 Join us! ✅",
    ],
    "premier league": [
        "Official PL supporter community. The biggest football league, the biggest fanbase ✅ #PL",
        "Premier League fans worldwide — official supporter trust on ConnectDial 🏴󠁧󠁢󠁥󠁮󠁧󠁿 ✅",
        "Matchday. Every matchday. The official EPL community on ConnectDial ✅ #PremierLeague",
    ],
    "champions league": [
        "Official UCL supporter community. European nights covered live ⭐ ✅ #ChampionsLeague",
        "Champions League fan network. Budapest final 2026 — we'll be there 🏆 ✅ #UCL",
    ],
    "la liga": [
        "Official La Liga fan community on ConnectDial 🇪🇸 El Clásico · Every game ✅",
        "LaLiga supporters trust. Barcelona champions 2025-26 🔵🔴 ✅ #LaLiga",
    ],
    "serie a": [
        "Official Serie A fan community. Inter champions 2025-26 🖤💙 ✅ #SerieA",
        "Italian football supporter network on ConnectDial ✅ #Calcio #SerieA",
    ],
    "bundesliga": [
        "Official Bundesliga supporter community 🇩🇪 Kane 33 goals. Bayern 34th title ✅",
        "German football fan trust on ConnectDial. The Yellow Wall never sleeps ✅ #Bundesliga",
    ],
    "nba": [
        "Official NBA fan community on ConnectDial 🏀 OKC defending champs ✅ #NBA",
        "Basketball supporters network. Playoffs coverage, every round ✅ #NBA #ConnectDial",
    ],
    "fifa world cup": [
        "FIFA World Cup 2026 official fan community. 48 nations 🏆🌍 ✅ #WC2026",
        "World Cup 2026 supporter network — USA, Mexico, Canada. Everyone welcome ✅ #FIFA2026",
        "The global football community for WC2026. Join millions of fans ✅ #WorldCup2026",
    ],
    "generic": [
        "Official {league} fan community on ConnectDial ✅ Join us!",
        "Supporting {league} worldwide. Verified supporter organisation ✅ #ConnectDial",
        "{league} fans united. Official community account ✅",
    ],
}

# ─── IMAGE SEARCH TERMS BY TYPE ──────────────────────────────────────────────
IMAGE_SEARCHES = {
    "news": [
        "sports journalist broadcast studio",
        "sports news presenter television",
        "sports reporter microphone stadium",
        "football analyst desk television",
        "sports broadcaster press conference",
    ],
    "organization": [
        "football supporters club banner stadium",
        "football fans tifo ultras",
        "sports club badge trophy cabinet",
        "football stadium exterior architecture",
        "supporters group football scarf",
    ],
}


class Command(BaseCommand):
    help = 'Creates news and organisation bot accounts with Apify-sourced images'

    def add_arguments(self, parser):
        parser.add_argument('total', type=int, help='Number of pro bots to create')
        parser.add_argument('--type', choices=['news', 'organization', 'both'],
                            default='both', help='Which account type to create')
        parser.add_argument('--league', type=str, default=None,
                            help='Target specific league (optional)')

    # ── APIFY IMAGE FETCH ─────────────────────────────────────────────────────
    def _fetch_image_apify(self, search_term):
        """
        Uses Apify Google Images Scraper to get varied, relevant images.
        Actor: apify~google-images-scraper
        Falls back silently if token not set.
        """
        if not APIFY_TOKEN:
            return None
        try:
            r = requests.post(
                "https://api.apify.com/v2/acts/apify~google-images-scraper"
                "/run-sync-get-dataset-items",
                params={"token": APIFY_TOKEN},
                json={
                    "queries": search_term,
                    "maxImagesPerQuery": 10,
                    "imageSize": "medium",
                    "safesearch": "active",
                },
                timeout=45,
            )
            if r.status_code != 200:
                return None
            items = r.json()
            if not items:
                return None
            # Pick a random result from the top 8
            item = random.choice(items[:8])
            img_url = item.get("imageUrl") or item.get("url")
            if not img_url:
                return None
            res = requests.get(img_url,
                               headers={"User-Agent": "Mozilla/5.0"},
                               timeout=15)
            if res.status_code == 200 and len(res.content) > 3000:
                return res.content
        except Exception:
            pass
        return None

    # ── PEXELS IMAGE FETCH ────────────────────────────────────────────────────
    def _fetch_image_pexels(self, search_term):
        if not PEXELS_API_KEY:
            return None
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": search_term, "per_page": 15,
                        "orientation": "square"},
                headers={"Authorization": PEXELS_API_KEY},
                timeout=8,
            ).json()
            photos = r.get("photos", [])
            if photos:
                photo = random.choice(photos[:8])
                img_url = photo.get("src", {}).get("medium")
                if img_url:
                    res = requests.get(img_url,
                                       headers={"User-Agent": "Mozilla/5.0"},
                                       timeout=12)
                    if res.status_code == 200:
                        return res.content
        except Exception:
            pass
        return None

    # ── PIXABAY IMAGE FETCH ───────────────────────────────────────────────────
    def _fetch_image_pixabay(self, search_term):
        if not PIXABAY_API_KEY:
            return None
        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={"key": PIXABAY_API_KEY,
                        "q": search_term.replace(" ", "+"),
                        "image_type": "photo", "per_page": 10,
                        "safesearch": "true"},
                timeout=8,
            ).json()
            hits = r.get("hits", [])
            if hits:
                hit = random.choice(hits[:8])
                img_url = hit.get("webformatURL")
                if img_url:
                    res = requests.get(img_url,
                                       headers={"User-Agent": "Mozilla/5.0"},
                                       timeout=12)
                    if res.status_code == 200:
                        return res.content
        except Exception:
            pass
        return None

    def _fetch_image(self, acc_type, custom_term=None):
        """
        3-source cascade: Apify → Pexels → Pixabay.
        Uses a role-appropriate search term.
        """
        pool   = IMAGE_SEARCHES.get(acc_type, IMAGE_SEARCHES["news"])
        term   = custom_term or random.choice(pool)

        # 1. Apify (most varied)
        img = self._fetch_image_apify(term)
        if img:
            self.stdout.write(f"    📸 Apify image: {term}")
            return img

        # 2. Pexels
        img = self._fetch_image_pexels(term)
        if img:
            self.stdout.write(f"    📸 Pexels image: {term}")
            return img

        # 3. Pixabay
        img = self._fetch_image_pixabay(term)
        if img:
            self.stdout.write(f"    📸 Pixabay image: {term}")
            return img

        self.stdout.write(self.style.WARNING(f"    ⚠️  All image sources failed: {term}"))
        return None

    # ── BRANDED NAME ──────────────────────────────────────────────────────────
    def _branded_name(self, acc_type, league, used_names):
        brands = LEAGUE_BRANDS.get(league.name.lower(), {})
        pool   = brands.get("news" if acc_type == "news" else "org", [])
        if pool:
            unused = [n for n in pool if n not in used_names]
            if unused:
                return random.choice(unused)
        # Fallback generated name
        if acc_type == "news":
            return f"{random.choice(NEWS_PREFIXES)} {league.name} {random.choice(NEWS_SUFFIXES)}"
        return f"{league.name} {random.choice(ORG_TYPES)}"

    # ── BIO ───────────────────────────────────────────────────────────────────
    def _build_bio(self, acc_type, league):
        ln   = league.name.lower()
        pool = (NEWS_BIOS if acc_type == "news" else ORGANIZATION_BIOS)
        bio  = random.choice(pool.get(ln, pool["generic"]))
        return bio.format(league=league.name)

    # ── BANNER IMAGE ──────────────────────────────────────────────────────────
    def _fetch_banner(self, league_name):
        """Stadium/league banner via Pexels landscape search."""
        sport = league_name.split()[0].lower()
        term  = f"{sport} stadium crowd atmosphere"
        if PEXELS_API_KEY:
            try:
                r = requests.get(
                    "https://api.pexels.com/v1/search",
                    params={"query": term, "per_page": 10,
                            "orientation": "landscape"},
                    headers={"Authorization": PEXELS_API_KEY},
                    timeout=8,
                ).json()
                photos = r.get("photos", [])
                if photos:
                    photo = random.choice(photos[:5])
                    url   = photo.get("src", {}).get("large")
                    if url:
                        res = requests.get(url, timeout=12)
                        if res.status_code == 200:
                            return res.content
            except Exception:
                pass
        return None

    # ── MAIN ──────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        total        = options["total"]
        type_filter  = options["type"]
        league_filter = options.get("league")

        leagues = list(League.objects.all())
        if league_filter:
            leagues = [l for l in leagues
                       if league_filter.lower() in l.name.lower()]
        if not leagues:
            self.stdout.write(self.style.ERROR("❌ No matching leagues in DB."))
            return

        self.stdout.write(f"🚀 Deploying {total} professional accounts "
                          f"(type={type_filter}) across {len(leagues)} league(s)...")
        if not APIFY_TOKEN:
            self.stdout.write(self.style.WARNING(
                "  ⚠️  APIFY_TOKEN not set — image cascade will skip Apify and use Pexels."
            ))

        used_names = set()
        created    = 0

        for i in range(total):
            # Alternate news / organization unless filtered
            if type_filter == "both":
                acc_type = "news" if i % 2 == 0 else "organization"
            else:
                acc_type = type_filter

            badge      = "official" if acc_type == "news" else "verified"
            fav_league = random.choice(leagues)
            suffix     = random.randint(100, 9999)

            display_name = self._branded_name(acc_type, fav_league, used_names)
            used_names.add(display_name)
            username = (
                display_name
                .replace(" ", "_").lower()
                .replace("'", "").replace("ñ", "n")
                .replace("é", "e").replace("ü", "u")
                + f"_{suffix}"
            )[:50]

            bio = self._build_bio(acc_type, fav_league)

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
                user.set_password("connect_pro_2026")
                user.save()

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.display_name = display_name
                profile.is_bot       = True
                profile.bio          = bio
                profile.save()

                type_icon = "📰" if acc_type == "news" else "🏛️"
                self.stdout.write(
                    f"\n  [{i+1}/{total}] {type_icon} {badge.upper()} "
                    f"→ {display_name} | {fav_league.name}"
                )

                # Profile image — Apify first
                img_data = self._fetch_image(acc_type)
                if img_data:
                    profile.profile_image.save(
                        f"pro_{user.id}.jpg",
                        ContentFile(img_data),
                        save=True,
                    )

                # Banner image — stadium from Pexels
                banner = self._fetch_banner(fav_league.name)
                if banner:
                    profile.banner_image.save(
                        f"banner_{user.id}.jpg",
                        ContentFile(banner),
                        save=True,
                    )
                    self.stdout.write(f"    🏟️  Banner assigned")

                created += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {username}: {e}"))

            time.sleep(0.8)

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {created}/{total} professional bots deployed!\n"
            f"   Types  : {type_filter}\n"
            f"   Leagues: {', '.join(l.name for l in leagues)}"
        ))