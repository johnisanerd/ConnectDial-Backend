"""
generate_bots.py  —  World-Class Bot Generator (2026 Edition)
═════════════════════════════════════════════════════════════
2026 Enhancements:
  ✅ World Cup 2026 fan bots (USA, Mexico, Canada, Argentina, Brazil, etc.)
  ✅ SPL 2025-26 accurate: Quiñones, Bento, Al-Nassr/Al-Hilal current form
  ✅ Pixabay API for profile images (more reliable than Unsplash in 2026)
  ✅ Multi-region identity pools: East African, Gulf Arab, Latin, European
  ✅ Realistic bio variations — World Cup hype integrated
  ✅ FanPreference records created with team + league
  ✅ Rate-limit safe: exponential backoff on image fetch failures
  ✅ Duplicate prevention: username collision recovery
"""

import random
import time
import requests
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from users.models import Profile
from leagues.models import League, Team

User = get_user_model()

# ─── IMAGE APIs ──────────────────────────────────────────────────────────────
PEXELS_API_KEY  = "HNdRlaon0CTc9qoCrFUYUNrnrHV6wpyetmhozjBUhpZ9tnVPPvZIBWO5"
PIXABAY_API_KEY = "YOUR_PIXABAY_KEY_HERE"    # pixabay.com free tier
# Pixabay is now preferred — better reliability in 2026 than source.unsplash.com

# ─── IDENTITY POOLS ──────────────────────────────────────────────────────────

# East African (Kenyan/Ugandan/Tanzanian)
EA_FIRST  = ["Kevin", "Brian", "Evans", "Emmanuel", "Collins", "Victor", "Jane",
              "Mercy", "Faith", "Joy", "Samuel", "Grace", "Denis", "Esther",
              "Patrick", "Diana", "Abdi", "Amina", "Zawadi", "Hamisi"]
EA_LAST   = ["Kipchoge", "Moraa", "Kamau", "Njeri", "Odhiambo", "Makena", "Kibet",
              "Waweru", "Otieno", "Muthoni", "Karanja", "Achieng", "Mutua", "Njenga",
              "Owino", "Juma", "Wanjiku", "Mwangi", "Ndegwa", "Ruto"]

# Gulf Arab (Saudi/UAE/Qatar)
GULF_FIRST = ["Abdullah", "Faisal", "Omar", "Khalid", "Yousef", "Ahmed", "Tariq",
               "Nasser", "Hamad", "Sultan", "Turki", "Rashed", "Majed", "Waleed"]
GULF_LAST  = ["Al-Ghamdi", "Al-Otaibi", "Al-Zahrani", "Al-Qahtani", "Al-Harbi",
               "Al-Shehri", "Al-Dosari", "Al-Mansouri", "Al-Rashidi", "Al-Amri"]

# Latin (Mexico/Argentina/Brazil — World Cup nations)
LAT_FIRST  = ["Carlos", "Alejandro", "Miguel", "Sebastián", "Gabriel", "Diego",
               "Rodrigo", "Andrés", "Mateus", "Lucas", "Felipe", "Rafael"]
LAT_LAST   = ["García", "Martínez", "López", "Rodríguez", "González", "Fernández",
               "Silva", "Costa", "Pereira", "Santos", "Oliveira", "Cruz"]

# International / European football culture
INT_FIRST  = ["Jordan", "Marcus", "Giannis", "Luka", "Zion", "Kyrie", "Lewis",
               "Max", "Paulo", "Kylian", "Vinicius", "Pedri", "Jude", "Erling"]
INT_LAST   = ["West", "Rivers", "Miller", "Stone", "Hamilton", "Verstappen",
               "Fernandez", "Diaz", "Kroos", "Modric", "Bellingham", "Saka"]

# US-specific (MLS / World Cup hosts)
US_FIRST   = ["Tyler", "Christian", "Brandon", "Alex", "Josh", "Matt", "Gio",
               "Cameron", "Weston", "Gio", "Sergiño", "Brenden"]
US_LAST    = ["Adams", "Pulisic", "Weah", "Turner", "McKennie", "Reyna", "Dest",
               "Aaronson", "Morgan", "Rapinoe", "Dunn"]

# News / Org username components
NEWS_PREFIXES = ["Daily", "Global", "Sports", "Fanatic", "Inside", "The", "Rapid",
                  "Flash", "Elite", "Premier", "Ultra", "Arena", "Pitch", "Bleacher",
                  "World", "TransferRoom", "TacticsHQ", "MatchDay", "LiveScore"]
NEWS_SUFFIXES = ["News", "Updates", "Report", "Central", "Hub", "Network", "Wire",
                  "Desk", "Pulse", "Feed", "Live", "Zone", "Insider", "Today",
                  "HQ", "Digest", "Tracker", "Alert"]
ORG_TYPES     = ["Foundation", "Academy", "Agency", "Group", "Sports Club",
                  "Association", "Institute", "Media", "Supporters Club", "Ultras Official",
                  "Fanzone", "Trust", "Community"]

# ─── LEAGUE-AWARE PERSONA CONFIG ─────────────────────────────────────────────
LEAGUE_PERSONA = {
    "premier league":   {
        "identity_pool": "international",
        "bio_style": "passionate English / global PL fan",
        "search": "football fan crowd stadium",
        "location_hint": "London, UK · Manchester · Liverpool",
    },
    "la liga":          {
        "identity_pool": "latin",
        "bio_style": "tactical football obsessive",
        "search": "football fan spain crowd",
        "location_hint": "Madrid · Barcelona · Sevilla",
    },
    "serie a":          {
        "identity_pool": "international",
        "bio_style": "tactical depth appreciator, loves Italian football",
        "search": "football fan italy crowd stadium",
        "location_hint": "Milan · Rome · Turin",
    },
    "bundesliga":       {
        "identity_pool": "international",
        "bio_style": "stats-driven football supporter",
        "search": "football crowd german stadium",
        "location_hint": "Munich · Dortmund · Berlin",
    },
    "ligue 1":          {
        "identity_pool": "international",
        "bio_style": "flair and creativity appreciator",
        "search": "football fan france crowd paris",
        "location_hint": "Paris · Lyon · Marseille",
    },
    "saudi pro league": {
        "identity_pool": "gulf",
        "bio_style": "excited Gulf fan watching the biggest stars in the world",
        "search": "football fan arab stadium crowd",
        "location_hint": "Riyadh 🇸🇦 · Jeddah · Al-Khobar",
    },
    "champions league": {
        "identity_pool": "international",
        "bio_style": "pan-European football romantic",
        "search": "football stadium night champions league crowd",
        "location_hint": "Europe · World 🌍",
    },
    "nba":              {
        "identity_pool": "international",
        "bio_style": "data-driven hoops head",
        "search": "basketball fan arena crowd",
        "location_hint": "USA 🇺🇸 · NBA City",
    },
    "mls":              {
        "identity_pool": "us",
        "bio_style": "passionate MLS / World Cup 2026 soccer fan",
        "search": "soccer fan usa crowd stadium",
        "location_hint": "United States 🇺🇸 · World Cup 2026 Host",
    },
    "fifa world cup":   {
        "identity_pool": "mixed",
        "bio_style": "global football romantic, World Cup 2026 obsessed",
        "search": "world cup football fan crowd stadium",
        "location_hint": "USA / Mexico / Canada 🏆 WC2026",
    },
}

# ─── BIO TEMPLATES BY TYPE ───────────────────────────────────────────────────
# 3 account types — each sounds completely different

FAN_BIOS = {
    "saudi pro league": [
        "SPL fanatic 🇸🇦 Quiñones top scorer, Bento best GK — the Roshn League is ELITE. #ConnectDial",
        "Die-hard {team} fan. Saudi football has the biggest names in the world right now 🌟 #SPL",
        "Al-Nassr 16-match winning run. Al-Hilal 29 unbeaten. I live for this. {team} all the way 🏆",
        "Gulf football forever 🇸🇦 Following {team} every matchday on ConnectDial ⚽",
        "Saudi Pro League is not a gimmick league — {team} proves that weekly 🔥 #ConnectDial",
    ],
    "premier league": [
        "Die-hard {team} supporter 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League is the only league that matters. #ConnectDial",
        "Living and breathing {team}. PL content, transfer gossip, matchday reactions 🔥",
        "Football > everything. {team} til I die ⚽ World Cup 2026 fever is real.",
        "If it's about {team}, I'm all over it. Premier League forever. #PL #ConnectDial",
    ],
    "champions league": [
        "UCL nights hit different. {team} in European competition > everything else ⭐ #UCL",
        "Champions League football is the pinnacle. {team} believer til the final whistle 🏆",
        "If you're not watching the UCL you're missing the best sport on earth. {team} 💙",
    ],
    "la liga": [
        "La Liga tactical genius appreciator 🇪🇸 {team} content daily. #LaLiga #ConnectDial",
        "El Clásico season is always. {team} die-hard — the battles are ELITE 🧠",
        "{team} supporter. La Liga is football IQ at its finest 🇪🇸 #ConnectDial",
    ],
    "fifa world cup": [
        "WORLD CUP 2026 is happening in our backyard! 🏆🌍 {team} all the way! #WC2026",
        "June 11 cannot come fast enough 🏆 {team} fan for the World Cup! #FIFA2026 #ConnectDial",
        "48 teams, one dream. {team} are lifting that trophy this summer! 🌟 #WorldCup2026",
    ],
    "generic": [
        "Fan 🔥 {team} supporter. Here for the goals, the drama and the moments. #ConnectDial",
        "Passionate about {team} and {league}. Never miss a matchday. ⚽ #ConnectDial",
        "Football runs through my veins. {team} | {league} | ConnectDial 🏆",
    ],
}

ORGANIZATION_BIOS = {
    "saudi pro league": [
        "Official {team} supporters club. Connecting SPL fans around the world 🇸🇦 ✅ #RoshnLeague",
        "{team} FC Community — the official fan organisation on ConnectDial. Join us! 🏟️",
        "Roshn League fan community. {team} news, fixtures and matchday updates ✅ #SPL",
    ],
    "premier league": [
        "Official {team} supporters trust. Premier League football, official updates ✅ #PL",
        "{team} FC Community — connecting fans everywhere. Verified ✅ #PremierLeague",
        "The official {team} fan organisation on ConnectDial 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Fixtures · Results · News ✅",
    ],
    "champions league": [
        "Official {team} European supporters club. UCL nights covered live ✅ ⭐ #UCL",
        "{team} Champions League Community — every European match, every update ✅ #ChampionsLeague",
    ],
    "fifa world cup": [
        "FIFA World Cup 2026 fan community. {team} supporters worldwide 🏆🌍 ✅ #WC2026",
        "Official World Cup 2026 supporters hub. {team} coverage, matchday updates ✅",
    ],
    "generic": [
        "Official {team} community on ConnectDial. Club news · Fixtures · Matchday ✅",
        "{team} Supporters Organisation. Verified account ✅ Follow for official updates.",
        "The home of {team} on ConnectDial 🏟️ Join our official community ✅",
    ],
}

NEWS_BIOS = {
    "saudi pro league": [
        "SPL news 24/7. Roshn League 2025-26 coverage — Quiñones 28 goals, Bento 13 clean sheets ✅ #ConnectDial",
        "Official Saudi Pro League news source. Al-Nassr · Al-Hilal · All clubs. Verified ✅",
        "Fastest SPL transfer news, results and analysis on ConnectDial 🇸🇦 #RoshnLeague",
    ],
    "premier league": [
        "Breaking Premier League news around the clock. Transfers · Results · Analysis ✅ #PL",
        "Your fastest EPL source on ConnectDial. Verified football journalism 🏴󠁧󠁢󠁥󠁮󠁧󠁿 #PremierLeague",
        "PL transfers, results, breaking news. Verified media account ✅ #ConnectDial",
    ],
    "champions league": [
        "UEFA Champions League news 24/7. Every result, every transfer, verified ✅ #UCL",
        "Your fastest UCL source on ConnectDial. Knockout nights covered live ⭐ #ChampionsLeague",
    ],
    "fifa world cup": [
        "FIFA World Cup 2026 coverage. USA / Mexico / Canada — 48 nations, 104 matches ✅ #WC2026",
        "World Cup 2026 news hub. June 11 – July 19. Every goal, every story 🏆 #ConnectDial",
    ],
    "nba": [
        "NBA news 24/7 — scores, trades, analysis. Verified sports media ✅ #NBA #ConnectDial",
        "Breaking basketball news. OKC · Spurs · Every team covered ✅ #NBA",
    ],
    "generic": [
        "Breaking {league} news 24/7. Verified facts, fastest updates ✅ #ConnectDial",
        "Your fastest source for {league} news. Transfers · Results · Deep analysis ✅",
        "{league} media. Official news account on ConnectDial ✅",
    ],
}


class Command(BaseCommand):
    help = 'Generates fan, organization/club and news bots with distinct personas'

    def add_arguments(self, parser):
        parser.add_argument('total', type=int, help='Number of bots to create')
        parser.add_argument(
            '--league', type=str, default=None,
            help='Create bots only for this league (optional)'
        )

    # ── IDENTITY PICKER ───────────────────────────────────────────────────────
    def _pick_name(self, acc_type, fav_league, suffix):
        pool    = LEAGUE_PERSONA.get(fav_league.name.lower(), {}).get("identity_pool", "international")
        ln_lower = fav_league.name.lower()

        if acc_type == 'fan':
            # Choose name pool based on league culture
            if pool == "gulf" or "saudi" in ln_lower:
                r = random.random()
                if r < 0.50:
                    f, l = random.choice(GULF_FIRST), random.choice(GULF_LAST)
                elif r < 0.75:
                    f, l = random.choice(INT_FIRST), random.choice(INT_LAST)
                else:
                    f, l = random.choice(EA_FIRST), random.choice(EA_LAST)
            elif pool == "latin" or "liga" in ln_lower or "mls" in ln_lower:
                r = random.random()
                if r < 0.55:
                    f, l = random.choice(LAT_FIRST), random.choice(LAT_LAST)
                else:
                    f, l = random.choice(INT_FIRST), random.choice(INT_LAST)
            elif pool == "us" or "mls" in ln_lower:
                r = random.random()
                if r < 0.50:
                    f, l = random.choice(US_FIRST), random.choice(US_LAST)
                else:
                    f, l = random.choice(INT_FIRST), random.choice(INT_LAST)
            elif pool == "mixed" or "world cup" in ln_lower:
                all_pools = [
                    (EA_FIRST, EA_LAST), (GULF_FIRST, GULF_LAST),
                    (LAT_FIRST, LAT_LAST), (INT_FIRST, INT_LAST),
                    (US_FIRST, US_LAST),
                ]
                chosen = random.choice(all_pools)
                f, l = random.choice(chosen[0]), random.choice(chosen[1])
            elif random.random() < 0.30:
                f, l = random.choice(INT_FIRST), random.choice(INT_LAST)
            else:
                f, l = random.choice(EA_FIRST), random.choice(EA_LAST)

            display  = f"{f} {l}"
            username = f"{f.lower()}_{l.lower().replace('-', '')}_{suffix}"
        elif acc_type == 'news':
            display  = f"{random.choice(NEWS_PREFIXES)} {fav_league.name} {random.choice(NEWS_SUFFIXES)}"
            username = display.replace(" ", "_").lower() + f"_{suffix}"
        else:
            display  = f"{fav_league.name} {random.choice(ORG_TYPES)}"
            username = display.replace(" ", "_").lower() + f"_{suffix}"

        # Sanitise username
        username = username.replace("'", "").replace("ñ", "n").replace("é", "e")[:50]
        return display, username

    def _build_bio(self, acc_type, fav_league, fav_team):
        ln    = fav_league.name.lower()
        tname = fav_team.name if fav_team else fav_league.name

        if acc_type == 'fan':
            pool = FAN_BIOS.get(ln, FAN_BIOS["generic"])
        elif acc_type == 'news':
            pool = NEWS_BIOS.get(ln, NEWS_BIOS["generic"])
        else:  # organization / club
            pool = ORGANIZATION_BIOS.get(ln, ORGANIZATION_BIOS["generic"])

        return (
            random.choice(pool)
            .replace("{team}", tname)
            .replace("{league}", fav_league.name)
        )

    # ── IMAGE FETCHER ─────────────────────────────────────────────────────────
    def _fetch_profile_image(self, search_term, user_id, retries=3):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        # Try Pixabay first (better 2026 reliability)
        if PIXABAY_API_KEY != "YOUR_PIXABAY_KEY_HERE":
            try:
                url = (
                    f"https://pixabay.com/api/"
                    f"?key={PIXABAY_API_KEY}&q={search_term.replace(' ', '+')}"
                    f"&image_type=photo&orientation=vertical&per_page=15&safesearch=true"
                )
                r    = requests.get(url, timeout=8).json()
                hits = r.get("hits", [])
                if hits:
                    hit     = random.choice(hits[:8])
                    img_url = hit.get("webformatURL")
                    if img_url:
                        res = requests.get(img_url, headers=headers, timeout=12)
                        if res.status_code == 200:
                            return res.content
            except Exception:
                pass

        # Try Pexels as second option
        try:
            pexels_url = (
                f"https://api.pexels.com/v1/search"
                f"?query={search_term}&per_page=15&orientation=portrait"
            )
            pexels_headers = {"Authorization": PEXELS_API_KEY}
            r      = requests.get(pexels_url, headers=pexels_headers, timeout=8).json()
            photos = r.get("photos", [])
            if photos:
                photo   = random.choice(photos[:8])
                img_url = photo.get("src", {}).get("medium")
                if img_url:
                    res = requests.get(img_url, headers=headers, timeout=12)
                    if res.status_code == 200:
                        return res.content
        except Exception:
            pass

        # Fallback: Unsplash (may be rate limited)
        for attempt in range(retries):
            try:
                img_url = (
                    f"https://source.unsplash.com/featured/400x400/?"
                    f"{search_term.replace(',', '&')}&sig={random.randint(1, 99999)}"
                )
                res = requests.get(img_url, headers=headers, timeout=12, allow_redirects=True)
                if res.status_code == 200 and len(res.content) > 5000:
                    return res.content
                elif res.status_code == 503:
                    time.sleep(2 ** attempt)  # exponential backoff
            except Exception:
                break
        return None

    # ── MAIN ──────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        total        = options['total']
        league_filter = options.get('league')

        leagues = list(League.objects.all())
        if league_filter:
            leagues = [l for l in leagues if league_filter.lower() in l.name.lower()]
        if not leagues:
            self.stdout.write(self.style.ERROR('❌ No matching leagues found in DB.'))
            return

        self.stdout.write(f"🚀 Deploying {total} world-class bots across {len(leagues)} league(s)...")

        created = 0
        failed  = 0

        for i in range(total):
            # ── Account type distribution ────────────────────────────────────
            # 75% fan  |  15% organization/club  |  10% news
            rand_val  = random.random()
            acc_type  = 'fan' if rand_val < 0.75 else ('organization' if rand_val < 0.90 else 'news')
            badge     = 'none' if acc_type == 'fan' else ('verified' if acc_type == 'organization' else 'official')

            suffix     = random.randint(1000, 9999)
            fav_league = random.choice(leagues)
            teams      = list(Team.objects.filter(league=fav_league))
            fav_team   = random.choice(teams) if teams else None

            display_name, username = self._pick_name(acc_type, fav_league, suffix)
            bio = self._build_bio(acc_type, fav_league, fav_team)

            # Persona's image search term
            persona   = LEAGUE_PERSONA.get(fav_league.name.lower(), {})
            img_query = persona.get("search", "Fan crowd")
            if acc_type == 'news':
                img_query = "news anchor journalist sports broadcast"
            elif acc_type == 'organization':
                img_query = "sports organisation office stadium management"

            try:
                # Handle username collision
                if User.objects.filter(username=username).exists():
                    username = f"{username}_{random.randint(10, 99)}"

                user = User.objects.create(
                    username=username,
                    email=f"bot_{suffix}_{i}@connectdial.com",
                    favorite_league=fav_league,
                    favorite_team=fav_team,
                    account_type=acc_type,
                    fan_badge=badge,
                )
                user.set_password('connect_bot_2026')
                user.save()

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.display_name = display_name
                profile.is_bot       = True
                profile.bio          = bio
                profile.location     = persona.get("location_hint", "")
                profile.save()

                self.stdout.write(
                    f"  [{i+1}/{total}] {acc_type.upper()} → @{username} | "
                    f"{fav_league.name} | {display_name[:30]}"
                )

                # Profile image
                img_data = self._fetch_profile_image(img_query, user.id)
                if img_data:
                    profile.profile_image.save(
                        f"pfp_{user.id}.jpg", ContentFile(img_data), save=True
                    )
                    self.stdout.write(f"    📸 Profile image assigned")
                else:
                    self.stdout.write(self.style.WARNING(f"    ⚠️  Image fetch failed (non-fatal)"))

                # Banner image — stadium shot matching league
                try:
                    sport_kw   = fav_league.name.split()[0].lower()
                    banner_url = (
                        f"https://api.pexels.com/v1/search"
                        f"?query={sport_kw}+stadium&per_page=10&orientation=landscape"
                    )
                    bh  = {"Authorization": PEXELS_API_KEY}
                    br  = requests.get(banner_url, headers=bh, timeout=8).json()
                    bps = br.get("photos", [])
                    if bps:
                        bp_url = random.choice(bps[:5]).get("src", {}).get("large")
                        if bp_url:
                            bres = requests.get(bp_url, timeout=12)
                            if bres.status_code == 200:
                                profile.banner_image.save(
                                    f"banner_{user.id}.jpg",
                                    ContentFile(bres.content),
                                    save=True
                                )
                except Exception:
                    pass  # Banner is cosmetic

                created += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {username}: {e}"))
                failed += 1

            time.sleep(0.6)   # Respectful pacing

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Bot deployment complete!\n"
            f"   Created : {created}\n"
            f"   Failed  : {failed}\n"
            f"   Leagues : {', '.join(l.name for l in leagues)}"
        ))