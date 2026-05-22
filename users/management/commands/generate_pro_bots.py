import random
import requests
import time
from django.core.management.based import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from users.models import Profile
from leagues.models import League

User = get_user_model()

NEWS_PREFIXES = ["Daily","Global","Sports","Fanatic","Inside","The","Rapid","Flash",
                  "Elite","Premier","Ultra","Arena","Pitch","Bleacher","TransferRoom"]
NEWS_SUFFIXES = ["News","Updates","Report","Central","Hub","Network","Wire","Desk",
                  "Pulse","Feed","Live","Zone","Insider","Today","HQ"]
ORG_TYPES     = ["Foundation","Academy","Agency","Group","Sports Club",
                  "Association","Institute","Media","Supporters Club","Ultras Official"]

# League-specific org/media branding flavours
LEAGUE_BRANDS = {
    "saudi pro league": {
        "news": ["Roshn League Pulse", "Al-Dawri Insider", "SPL Wire", "Gulf Football Report"],
        "org":  ["Saudi Football Foundation", "SPL Supporters HQ", "Gulf Football Academy"],
    },
    "premier league": {
        "news": ["EPL Central", "Premier Wire", "TopFlight Report", "Matchday Live"],
        "org":  ["PL Supporters Trust", "Three Lions Academy", "Premier Football Group"],
    },
    "champions league": {
        "news": ["UCL Insider", "European Nights Report", "Champions Wire"],
        "org":  ["UCL Supporters Club", "European Football Academy"],
    },
}


class Command(BaseCommand):
    help = 'Generates Official News and Organization bots with league-aware branding'

    def add_arguments(self, parser):
        parser.add_argument('total', type=int, help='Number of Pro bots to create')

    def _branded_name(self, acc_type, league):
        """Try a league-specific pre-built brand name first, fall back to generated."""
        league_lower = league.name.lower()
        brands = LEAGUE_BRANDS.get(league_lower, {})
        pool   = brands.get('news' if acc_type == 'news' else 'org', [])
        if pool:
            return random.choice(pool)
        # Generated fallback
        if acc_type == 'news':
            return f"{random.choice(NEWS_PREFIXES)} {league.name} {random.choice(NEWS_SUFFIXES)}"
        return f"{league.name} {random.choice(ORG_TYPES)}"

    def handle(self, *args, **options):
        total   = options['total']
        leagues = list(League.objects.all())
        if not leagues:
            self.stdout.write(self.style.ERROR('❌ No leagues found in DB.'))
            return

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        self.stdout.write(f"🚀 Deploying {total} Professional Accounts...")

        for i in range(total):
            acc_type   = 'news' if i % 2 == 0 else 'organization'
            badge      = 'official' if acc_type == 'news' else 'verified'
            fav_league = random.choice(leagues)
            suffix     = random.randint(100, 999)

            display_name = self._branded_name(acc_type, fav_league)
            username     = display_name.replace(" ", "_").lower() + f"_{suffix}"

            if acc_type == 'news':
                bio          = (f"Verified {fav_league.name} news source. "
                                f"Transfers · Results · Analysis — {display_name} ✅")
                search_term  = "news,studio,journalism,sports broadcast"
            else:
                bio          = (f"Official {display_name} account. "
                                f"Promoting sports excellence in {fav_league.name} 🌍")
                search_term  = "stadium,office,sports management,organization"

            try:
                user = User.objects.create(
                    username=username,
                    email=f"pro_{suffix}@connectdial.com",
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

                self.stdout.write(f"  [{i+1}/{total}] {badge.upper()} → {display_name}")

                # Profile image
                try:
                    img_url = (f"https://source.unsplash.com/featured/400x400/?"
                               f"{search_term}&sig={random.randint(1, 9999)}")
                    res = requests.get(img_url, headers=headers, timeout=6)
                    if res.status_code == 200:
                        profile.profile_image.save(f"pro_{user.id}.jpg",
                                                    ContentFile(res.content), save=True)
                except Exception as img_err:
                    self.stdout.write(self.style.WARNING(f"    ⚠️ Image skip: {img_err}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {username}: {e}"))

            time.sleep(0.8)

        self.stdout.write(self.style.SUCCESS(f'✅ {total} Professional bots deployed!'))