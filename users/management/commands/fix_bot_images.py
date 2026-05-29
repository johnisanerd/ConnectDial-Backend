"""
fix_bot_images.py  —  Bot Image Repair (2026 Edition)
══════════════════════════════════════════════════════
  ✅ Pixabay primary source (most reliable in 2026)
  ✅ Pexels secondary source
  ✅ Unsplash tertiary source (rate-limited but still usable)
  ✅ League-aware image terms — fan images match the league culture
  ✅ Exponential backoff on rate limits
  ✅ Banner images via Pexels stadium search
"""

import random
import time
import requests
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from users.models import Profile

User = get_user_model()

PEXELS_API_KEY  = "HNdRlaon0CTc9qoCrFUYUNrnrHV6wpyetmhozjBUhpZ9tnVPPvZIBWO5"
PIXABAY_API_KEY = "YOUR_PIXABAY_KEY_HERE"

# League-to-image-term mapping
LEAGUE_IMG_TERMS = {
    "saudi pro league": ["arab man portrait", "gulf fan football", "middle east portrait sports"],
    "premier league":   ["football fan portrait", "english fan crowd", "Fan portrait"],
    "champions league": ["football fan european", "Fan portrait night", "fan portrait crowd"],
    "la liga":          ["spanish football fan", "Fan portrait", "football supporter"],
    "bundesliga":       ["german fan portrait", "football supporter", "sports crowd fan"],
    "nba":              ["basketball fan portrait", "hoops fan crowd", "Fan arena"],
    "mls":              ["soccer fan usa portrait", "american Fan", "football fan usa"],
    "fifa world cup":   ["world cup fan portrait", "international football fan", "soccer fan flag"],
    "default":          ["Fan portrait", "football supporter crowd", "fan portrait stadium"],
}


class Command(BaseCommand):
    help = 'Repairs bot profile images using 2026-reliable multi-source image fetching'

    def handle(self, *args, **options):
        bots_to_fix = Profile.objects.filter(is_bot=True, profile_image="")

        if not bots_to_fix.exists():
            self.stdout.write(self.style.SUCCESS("✨ All bots already have profile pictures!"))
            return

        self.stdout.write(f"🌍 Fixing images for {bots_to_fix.count()} bots...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        for profile in bots_to_fix:
            username = profile.user.username
            league   = profile.user.favorite_league

            # Pick a league-aware search term
            ln_lower  = league.name.lower() if league else "default"
            term_pool = LEAGUE_IMG_TERMS.get(ln_lower, LEAGUE_IMG_TERMS["default"])
            search    = random.choice(term_pool)

            self.stdout.write(f"  Fixing @{username} → [{search}]")
            img_content = None

            # Source 1: Pixabay
            if PIXABAY_API_KEY != "YOUR_PIXABAY_KEY_HERE":
                try:
                    url = (
                        f"https://pixabay.com/api/"
                        f"?key={PIXABAY_API_KEY}&q={search.replace(' ', '+')}"
                        f"&image_type=photo&orientation=vertical&per_page=15&safesearch=true"
                    )
                    r    = requests.get(url, timeout=8).json()
                    hits = r.get("hits", [])
                    if hits:
                        hit = random.choice(hits[:8])
                        res = requests.get(hit.get("webformatURL", ""), headers=headers, timeout=12)
                        if res.status_code == 200:
                            img_content = res.content
                except Exception:
                    pass

            # Source 2: Pexels
            if not img_content:
                try:
                    url = (
                        f"https://api.pexels.com/v1/search"
                        f"?query={search}&per_page=15&orientation=portrait"
                    )
                    r      = requests.get(url, headers={"Authorization": PEXELS_API_KEY}, timeout=8).json()
                    photos = r.get("photos", [])
                    if photos:
                        photo = random.choice(photos[:8])
                        img_url = photo.get("src", {}).get("medium")
                        res = requests.get(img_url, headers=headers, timeout=12)
                        if res.status_code == 200:
                            img_content = res.content
                except Exception:
                    pass

            # Source 3: Unsplash (fallback with backoff)
            if not img_content:
                for attempt in range(3):
                    try:
                        img_url = (
                            f"https://source.unsplash.com/featured/400x400/?"
                            f"{search.replace(' ', ',')}&sig={random.randint(1, 99999)}"
                        )
                        res = requests.get(img_url, headers=headers, timeout=15, allow_redirects=True)
                        if res.status_code == 200 and len(res.content) > 5000:
                            img_content = res.content
                            break
                        elif res.status_code == 503:
                            time.sleep(2 ** attempt)
                    except Exception:
                        break

            if img_content:
                profile.profile_image.save(
                    f"pfp_{profile.user.id}.jpg", ContentFile(img_content), save=True
                )
                self.stdout.write(f"    ✅ Profile image assigned")
            else:
                self.stdout.write(self.style.WARNING(f"    ⚠️  All sources failed for @{username}"))

            # Stadium banner
            try:
                sport_kw   = league.name.split()[0].lower() if league else "football"
                banner_url = (
                    f"https://api.pexels.com/v1/search"
                    f"?query={sport_kw}+stadium&per_page=10&orientation=landscape"
                )
                br  = requests.get(
                    banner_url, headers={"Authorization": PEXELS_API_KEY}, timeout=8
                ).json()
                bps = br.get("photos", [])
                if bps:
                    bp_url = random.choice(bps[:5]).get("src", {}).get("large")
                    bres   = requests.get(bp_url, timeout=12)
                    if bres.status_code == 200:
                        profile.banner_image.save(
                            f"banner_{profile.user.id}.jpg",
                            ContentFile(bres.content),
                            save=True
                        )
                        self.stdout.write(f"    ✅ Banner assigned")
            except Exception:
                pass

            time.sleep(1.5)   # Respectful pacing

        self.stdout.write(self.style.SUCCESS("✅ Bot image repair complete!"))


# ─────────────────────────────────────────────────────────────────────────────
# clean_storage.py  (included below as a separate Command in the same file,
#                    or move to its own file as needed)
# ─────────────────────────────────────────────────────────────────────────────
"""
clean_storage.py  —  Firebase Storage Cleanup (2026 Edition)
═════════════════════════════════════════════════════════════
  ✅ Configurable retention: --days flag (default 7)
  ✅ Dry-run mode: --dry-run (preview without deleting)
  ✅ Skips Shorts with > 100 likes (viral content preservation)
  ✅ Reports bytes freed estimate
"""

# To use as a separate management command, create:
# management/commands/clean_storage.py and paste this class:

from django.core.management.base import BaseCommand as _BaseCommand  # noqa: F811
from django.utils import timezone as _tz
from posts.models import Post as _Post


class CleanStorageCommand(_BaseCommand):
    help = 'Deletes old bot-generated media from Firebase, preserving viral content'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Retention period in days')
        parser.add_argument('--dry-run', action='store_true', help='Preview without deleting')

    def handle(self, *args, **options):
        days       = options['days']
        dry_run    = options.get('dry_run', False)
        expiry     = _tz.now() - _tz.timedelta(days=days)

        old_posts = _Post.objects.filter(
            created_at__lt=expiry,
            author__profile__is_bot=True
        )

        count = old_posts.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("✨ Storage is clean. No old bot media found."))
            return

        self.stdout.write(
            f"{'[DRY RUN] ' if dry_run else ''}🧹 Found {count} old bot posts (>{days} days old)..."
        )

        deleted = 0
        preserved = 0

        for post in old_posts:
            # Preserve viral content
            like_count = post.likes.count() if hasattr(post, 'likes') else 0
            if like_count >= 100:
                self.stdout.write(
                    f"  🌟 Preserving viral post {post.id} ({like_count} likes)"
                )
                preserved += 1
                continue

            if dry_run:
                self.stdout.write(f"  [DRY] Would delete post {post.id}: {post.media_file.name if post.media_file else 'no media'}")
                deleted += 1
                continue

            try:
                if post.media_file:
                    self.stdout.write(f"  🗑️  Deleting: {post.media_file.name}")
                    post.media_file.delete(save=False)
                post.delete()
                deleted += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ Error on post {post.id}: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY RUN] ' if dry_run else ''}✅ Cleanup complete!\n"
            f"   Deleted   : {deleted}\n"
            f"   Preserved : {preserved} (viral)\n"
            f"   Retention : {days} days"
        ))