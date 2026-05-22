import random
import requests
import time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from users.models import Profile, FanPreference
from leagues.models import League, Team

User = get_user_model()

# ─────────────────────────────────────────────
#  IDENTITY POOLS  (richer, more realistic)
# ─────────────────────────────────────────────
KE_FIRST   = ["Kevin","Brian","Evans","Emmanuel","Collins","Victor","Jane","Mercy",
               "Faith","Joy","Samuel","Grace","Denis","Esther","Patrick","Diana"]
KE_ETHNIC  = ["Kipchoge","Moraa","Kamau","Njeri","Odhiambo","Makena","Kibet",
               "Waweru","Otieno","Muthoni","Karanja","Achieng","Mutua","Njenga"]

INT_FIRST  = ["Jordan","Marcus","Giannis","Luka","Zion","Kyrie","Lewis","Max",
               "Paulo","Kylian","Vinicius","Pedri","Bellingham","Haaland","Saka"]
INT_LAST   = ["West","Rivers","Miller","Stone","Hamilton","Verstappen","Bryant",
               "Fernandez","Diaz","Kroos","Modric","Benzema","Salah","Kane"]

# Saudi-specific names (SPL has huge fanbase)
SA_FIRST   = ["Abdullah","Faisal","Omar","Khalid","Yousef","Ahmed","Tariq","Nasser"]
SA_LAST    = ["Al-Ghamdi","Al-Otaibi","Al-Zahrani","Al-Qahtani","Al-Harbi","Al-Shehri"]

NEWS_PREFIXES = ["Daily","Global","Sports","Fanatic","Inside","The","Rapid","Flash",
                  "Elite","Premier","Ultra","Arena","Pitch","Bleacher"]
NEWS_SUFFIXES = ["News","Updates","Report","Central","Hub","Network","Wire","Desk",
                  "Pulse","Feed","Live","Zone","Insider"]
ORG_TYPES     = ["Foundation","Academy","Agency","Group","Sports Club",
                  "Association","Institute","Media","FC Supporters","Ultras"]

# League → persona flavour map
LEAGUE_PERSONA = {
    "premier league": {"lang": "en", "style": "passionate English fan"},
    "la liga":        {"lang": "es", "style": "tactical obsessive"},
    "serie a":        {"lang": "it", "style": "tactical analyst"},
    "bundesliga":     {"lang": "de", "style": "stats-driven supporter"},
    "ligue 1":        {"lang": "fr", "style": "flair appreciator"},
    "saudi pro league": {"lang": "ar_en", "style": "excited Gulf fan watching the stars"},
    "nba":            {"lang": "en", "style": "data-driven hoops head"},
    "champions league": {"lang": "en", "style": "pan-European football romantic"},
    "mls":            {"lang": "en", "style": "growing soccer culture fan"},
}


class Command(BaseCommand):
    help = 'Generates high-fidelity bots (Fans, News, Orgs) with league-aware personas'

    def add_arguments(self, parser):
        parser.add_argument('total', type=int, help='Number of bots to create')

    def _pick_name(self, acc_type, fav_league, news_prefixes, news_suffixes, org_types, suffix):
        league_lower = fav_league.name.lower()
        if acc_type == 'fan':
            # Saudi league → mix Saudi + International names
            if "saudi" in league_lower:
                pool_choice = random.random()
                if pool_choice < 0.40:
                    f, l = random.choice(SA_FIRST), random.choice(SA_LAST)
                elif pool_choice < 0.70:
                    f, l = random.choice(INT_FIRST), random.choice(INT_LAST)
                else:
                    f, l = random.choice(KE_FIRST), random.choice(KE_ETHNIC)
            elif random.random() < 0.25:
                f, l = random.choice(INT_FIRST), random.choice(INT_LAST)
            else:
                f, l = random.choice(KE_FIRST), random.choice(KE_ETHNIC)
            display = f"{f} {l}"
            username = f"{f.lower()}_{l.lower()}_{suffix}"
            return display, username
        elif acc_type == 'news':
            display = f"{random.choice(news_prefixes)} {fav_league.name} {random.choice(news_suffixes)}"
        else:
            display = f"{fav_league.name} {random.choice(org_types)}"
        username = display.replace(" ", "_").lower() + f"_{suffix}"
        return display, username

    def _build_bio(self, acc_type, fav_league, teams):
        league_lower = fav_league.name.lower()
        persona = LEAGUE_PERSONA.get(league_lower, {}).get("style", "sports fan")
        fav_team = random.choice(teams).name if teams else fav_league.name

        if acc_type == 'fan':
            bios = [
                f"Die-hard {fav_team} supporter. {persona.title()}. #ConnectDial",
                f"Living and breathing {fav_league.name}. Follow for {fav_team} content 🔥",
                f"If it's about {fav_team}, I'm all over it. {fav_league.name} forever.",
                f"Matchday is the only day that matters. {fav_team} til I die ⚽",
            ]
        elif acc_type == 'news':
            bios = [
                f"Breaking {fav_league.name} news 24/7. Transfers, results & more.",
                f"Your fastest source for {fav_league.name} updates. Verified ✅",
                f"All the {fav_league.name} action — live scores, transfers, analysis.",
            ]
        else:
            bios = [
                f"Supporting the growth of {fav_league.name} worldwide. Official Account ✅",
                f"Connecting {fav_league.name} fans globally. Join the community.",
            ]
        return random.choice(bios)

    def handle(self, *args, **options):
        total   = options['total']
        leagues = list(League.objects.all())
        if not leagues:
            self.stdout.write(self.style.ERROR('❌ No leagues found.'))
            return

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        for i in range(total):
            rand_val  = random.random()
            acc_type  = 'fan' if rand_val < 0.88 else ('news' if rand_val < 0.96 else 'organization')
            badge     = 'none' if acc_type == 'fan' else ('official' if acc_type == 'news' else 'verified')

            suffix     = random.randint(1000, 9999)
            fav_league = random.choice(leagues)
            teams      = list(Team.objects.filter(league=fav_league))
            fav_team   = random.choice(teams) if teams else None

            display_name, username = self._pick_name(
                acc_type, fav_league, NEWS_PREFIXES, NEWS_SUFFIXES, ORG_TYPES, suffix)
            bio = self._build_bio(acc_type, fav_league, teams)

            search_map = {
                'fan':          'portrait,person,sports fan',
                'news':         'news,studio,microphone,journalism',
                'organization': 'stadium,office,sports management',
            }
            search_term = search_map[acc_type]

            try:
                user = User.objects.create(
                    username=username,
                    email=f"bot_{suffix}@connectdial.com",
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
                profile.save()

                self.stdout.write(f"  [{i+1}/{total}] {acc_type.upper()} → @{username} | {fav_league.name}")

                # Profile image via Unsplash
                try:
                    img_url = (f"https://source.unsplash.com/featured/400x400/?"
                               f"{search_term}&sig={random.randint(1, 9999)}")
                    res = requests.get(img_url, headers=headers, timeout=6)
                    if res.status_code == 200:
                        profile.profile_image.save(f"pfp_{user.id}.jpg",
                                                    ContentFile(res.content), save=True)
                except Exception:
                    pass  # Non-fatal — image is cosmetic

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {username}: {e}"))

            time.sleep(0.8)

        self.stdout.write(self.style.SUCCESS(f'✅ Done — {total} intelligent bots deployed.'))