"""
bot_post.py  —  Intelligent Live Sports Post Bot
─────────────────────────────────────────────────
Data sources (in priority order):
  1. API-Football (rapid-api) — live fixtures, standings, top scorers
  2. NewsAPI          — breaking sports headlines
  3. Hard-coded rich templates per league  (offline fallback)

Run:
  python manage.py bot_post "Saudi Pro League"
  python manage.py bot_post "Premier League"
  python manage.py bot_post "Champions League"
"""

import random
import requests
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from posts.models import Post, Hashtag
from leagues.models import League, Team

User = get_user_model()

# ─── API KEYS ────────────────────────────────────────────────────────────────
NEWS_API_KEY      = "b6c80809d3904036baa2e07657c02831"   # newsapi.org
RAPID_API_KEY     = "YOUR_RAPIDAPI_KEY_HERE"              # rapidapi.com → API-Football
# ─────────────────────────────────────────────────────────────────────────────

# Map ConnectDial league names → API-Football league IDs
LEAGUE_API_IDS = {
    "premier league":   39,
    "la liga":          140,
    "serie a":          135,
    "bundesliga":       78,
    "ligue 1":          61,
    "champions league": 2,
    "saudi pro league": 307,
    "nba":              None,   # handled separately
    "mls":              253,
}

# Emoji map for leagues
LEAGUE_EMOJI = {
    "premier league":   "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "la liga":          "🇪🇸",
    "serie a":          "🇮🇹",
    "bundesliga":       "🇩🇪",
    "ligue 1":          "🇫🇷",
    "champions league": "⭐",
    "saudi pro league": "🇸🇦",
    "nba":              "🏀",
    "mls":              "🇺🇸",
}

# Rich offline templates  (used only when APIs fail)
OFFLINE_TEMPLATES = {
    "saudi pro league": [
        "🇸🇦 The Saudi Pro League is officially the most star-studded league on the planet right now. Ronaldo, Benzema, Neymar, Firmino — the list never ends! Who's your favourite star in the SPL? 🔥 #SaudiProLeague #ConnectDial",
        "🔥 Al-Hilal are looking UNSTOPPABLE this season. Six points clear and they haven't even hit top gear yet! Can anyone catch them? #AlHilal #SPL",
        "💰 Another week, another jaw-dropping transfer rumour from the Saudi Pro League. The Roshn League is changing football forever! #Transfers #SPL #ConnectDial",
        "⚽ Al-Nassr vs Al-Hilal — the biggest fixture in Asian football right now. Who wins the Derby of Riyadh? Drop your prediction below! 👇 #SPL",
        "🌍 The Saudi Pro League is attracting talent from every corner of the globe. Is this the new Ligue 1? Discuss! #SaudiFootball",
    ],
    "premier league": [
        "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League Matchday energy is DIFFERENT. No other league comes close for pure drama. Which fixture are you watching this weekend? 🍿 #PL",
        "⚡ The title race is wide open and I am HERE for it. Every single point matters now. Who lifts the trophy? #PremierLeague #ConnectDial",
        "🔴 Top 4 fight is getting SPICY. Four clubs for two spots — this is the best part of the season! #PremierLeague",
    ],
    "champions league": [
        "⭐ There is nothing on earth like a Champions League night. The anthem, the lights, the drama. Pure football theatre. #UCL #ConnectDial",
        "🏆 UCL knockout football is a completely different sport. Heart rate through the roof every single minute. Who goes all the way this year? #ChampionsLeague",
    ],
    "la liga": [
        "🇪🇸 La Liga is serving ELITE football right now. The tactical battles are on another level this season. #LaLiga #ConnectDial",
        "🔥 Clasico season is almost here. Madrid vs Barça — football stops for 90 minutes. Are you ready? #ElClasico #LaLiga",
    ],
    "generic": [
        "⚽ Football never sleeps and neither does ConnectDial. Stay locked in for the latest updates! #Sports #ConnectDial",
        "🔥 Big week in sports ahead — make sure you're following the right accounts for live updates! #ConnectDial",
    ],
}


class Command(BaseCommand):
    help = 'Fetches LIVE trending sports data and posts as an intelligent bot'

    def add_arguments(self, parser):
        parser.add_argument('league_name', type=str)
        parser.add_argument('--source', type=str, default='auto',
                            choices=['auto', 'apifootball', 'newsapi', 'template'],
                            help='Force a specific data source')

    # ── SOURCE 1: API-Football (fixtures + standings + scorers) ──────────────
    def fetch_apifootball(self, league_id, league_name):
        """Returns a rich post string built from live fixture / standings data."""
        base = "https://api-football-v1.p.rapidapi.com/v3"
        headers = {
            "X-RapidAPI-Key":  RAPID_API_KEY,
            "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
        }
        posts = []

        # a) Latest fixtures (last 3 days)
        try:
            r = requests.get(f"{base}/fixtures",
                             params={"league": league_id, "last": 5, "status": "FT"},
                             headers=headers, timeout=8).json()
            fixtures = r.get("response", [])
            if fixtures:
                fx = random.choice(fixtures[:3])
                home  = fx["teams"]["home"]["name"]
                away  = fx["teams"]["away"]["name"]
                gh    = fx["goals"]["home"]
                ga    = fx["goals"]["away"]
                emoji = LEAGUE_EMOJI.get(league_name.lower(), "⚽")
                winner = home if gh > ga else (away if ga > gh else None)
                if winner:
                    posts.append(
                        f"{emoji} FULL TIME: {home} {gh} – {ga} {away} | "
                        f"{winner} take all three points! What a result! 🔥 "
                        f"#{league_name.replace(' ','')} #ConnectDial"
                    )
                else:
                    posts.append(
                        f"{emoji} FULL TIME: {home} {gh} – {ga} {away} | "
                        f"Points shared in a hard-fought draw. "
                        f"#{league_name.replace(' ','')} #ConnectDial"
                    )
        except Exception:
            pass

        # b) Standings (league leader)
        try:
            r = requests.get(f"{base}/standings",
                             params={"league": league_id, "season": 2024},
                             headers=headers, timeout=8).json()
            standings = r.get("response", [{}])[0].get("league", {}).get("standings", [[]])[0]
            if standings:
                leader = standings[0]
                name   = leader["team"]["name"]
                pts    = leader["points"]
                gd     = leader["goalsDiff"]
                emoji  = LEAGUE_EMOJI.get(league_name.lower(), "📊")
                posts.append(
                    f"{emoji} STANDINGS: {name} lead {league_name} with {pts} pts "
                    f"(GD {'+' if gd >= 0 else ''}{gd}). "
                    f"Can anyone stop them? 👀 #{league_name.replace(' ','')} #ConnectDial"
                )
        except Exception:
            pass

        # c) Top scorers
        try:
            r = requests.get(f"{base}/players/topscorers",
                             params={"league": league_id, "season": 2024},
                             headers=headers, timeout=8).json()
            scorers = r.get("response", [])
            if scorers:
                top    = scorers[0]
                player = top["player"]["name"]
                team   = top["statistics"][0]["team"]["name"]
                goals  = top["statistics"][0]["goals"]["total"]
                emoji  = LEAGUE_EMOJI.get(league_name.lower(), "🥅")
                posts.append(
                    f"{emoji} TOP SCORER: {player} ({team}) leads {league_name} "
                    f"with {goals} goals this season! Golden Boot race is 🔥 "
                    f"#{league_name.replace(' ','')} #ConnectDial"
                )
        except Exception:
            pass

        return posts

    # ── SOURCE 2: NewsAPI ────────────────────────────────────────────────────
    def fetch_newsapi(self, league_name):
        url = (f"https://newsapi.org/v2/everything"
               f"?q={league_name.replace(' ', '%20')}&sortBy=publishedAt"
               f"&language=en&pageSize=20&apiKey={NEWS_API_KEY}")
        try:
            data     = requests.get(url, timeout=8).json()
            articles = data.get('articles', [])
            if not articles:
                return None, None
            article   = random.choice(articles[:10])
            title     = article.get('title', '')
            desc      = article.get('description', '') or ''
            source    = article['source']['name']
            image_url = article.get('urlToImage')
            # Build a native-feeling post (not a raw paste of the headline)
            emoji = LEAGUE_EMOJI.get(league_name.lower(), "📰")
            post  = (f"{emoji} {title}\n\n"
                     f"{desc[:200].strip()}{'...' if len(desc) > 200 else ''}\n\n"
                     f"(via {source}) #{league_name.replace(' ','')} #ConnectDial")
            return post, image_url
        except Exception:
            return None, None

    # ── SOURCE 3: Rich offline templates ────────────────────────────────────
    def offline_template(self, league_name):
        pool = OFFLINE_TEMPLATES.get(league_name.lower(),
                                     OFFLINE_TEMPLATES["generic"])
        return random.choice(pool)

    # ── MAIN ─────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        league_query = options['league_name']
        source_pref  = options['source']

        league = League.objects.filter(name__icontains=league_query).first()
        if not league:
            self.stdout.write(self.style.ERROR(f"League '{league_query}' not found."))
            return

        teams      = list(Team.objects.filter(league=league))
        target_team = random.choice(teams) if teams else None
        league_id   = LEAGUE_API_IDS.get(league.name.lower())

        # Recruit / find a bot
        bot = (User.objects.filter(profile__is_bot=True, favorite_league=league)
               .order_by('?').first())
        if not bot:
            bot = User.objects.filter(profile__is_bot=True).order_by('?').first()
            if not bot:
                self.stdout.write(self.style.ERROR("No bots found. Run generate_bots first."))
                return
            bot.favorite_league = league
            bot.favorite_team   = target_team
            bot.save()
            self.stdout.write(self.style.SUCCESS(f"Recruited {bot.username} → {league.name}"))

        content   = None
        image_url = None

        # ── Try sources in priority order ────────────────────────────────────
        if source_pref in ('auto', 'apifootball') and league_id and RAPID_API_KEY != "YOUR_RAPIDAPI_KEY_HERE":
            self.stdout.write(f"📡 Querying API-Football for {league.name}...")
            posts = self.fetch_apifootball(league_id, league.name)
            if posts:
                content = random.choice(posts)
                self.stdout.write(self.style.SUCCESS("  ✅ API-Football data retrieved"))

        if not content and source_pref in ('auto', 'newsapi'):
            self.stdout.write(f"📰 Falling back to NewsAPI for {league.name}...")
            content, image_url = self.fetch_newsapi(league.name)
            if content:
                self.stdout.write(self.style.SUCCESS("  ✅ NewsAPI data retrieved"))

        if not content:
            self.stdout.write(f"📋 Using rich offline template for {league.name}...")
            content = self.offline_template(league.name)

        # ── Create the Post ──────────────────────────────────────────────────
        post_type = 'image' if image_url else 'text'
        new_post  = Post.objects.create(
            author=bot,
            content=content,
            post_type=post_type,
            league=league,
            team=target_team,
            is_short=False,
        )

        if image_url:
            try:
                img_res = requests.get(image_url, timeout=6)
                if img_res.status_code == 200:
                    new_post.media_file.save(f"news_{new_post.id}.jpg",
                                             ContentFile(img_res.content), save=True)
            except Exception:
                pass

        # ── Hashtags ─────────────────────────────────────────────────────────
        tags = ["Sports", league.name.replace(" ", ""), "ConnectDial"]
        for t in tags:
            tag_obj, _ = Hashtag.objects.get_or_create(name=t)
            new_post.hashtags.add(tag_obj)

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ POSTED by @{bot.username}\n"
            f"   League : {league.name}\n"
            f"   Source : {'API-Football' if '– ' in content else ('NewsAPI' if 'via ' in content else 'Template')}\n"
            f"   Preview: {content[:120]}..."
        ))