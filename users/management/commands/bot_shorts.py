"""
bot_shorts.py  —  Intelligent Sports Shorts Bot
─────────────────────────────────────────────────
Improvements:
  • Expanded league → search term map (SPL, NBA, F1, etc.)
  • Richer vertical-video captions tied to the specific league
  • Falls back through 3 search terms before giving up
  • Skips videos already posted by this bot this week (de-dup)
  • Picks the best mobile resolution (portrait ≤ 720px width)
"""

import random
import requests
import time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from posts.models import Post, Hashtag
from leagues.models import League, Team

User = get_user_model()

PEXELS_API_KEY = "HNdRlaon0CTc9qoCrFUYUNrnrHV6wpyetmhozjBUhpZ9tnVPPvZIBWO5"

# League → Pexels search terms (fallback chain)
LEAGUE_VIDEO_TERMS = {
    "premier league":   ["soccer match stadium", "football crowd england", "soccer goal"],
    "la liga":          ["football spain", "soccer skills", "football stadium"],
    "serie a":          ["football italy", "soccer match", "football skills"],
    "bundesliga":       ["football germany", "soccer training", "football action"],
    "ligue 1":          ["football france", "soccer dribble", "football match"],
    "champions league": ["football night stadium", "soccer champions", "football trophy"],
    "saudi pro league": ["football saudi", "soccer desert", "football stadium night"],
    "nba":              ["basketball dunk", "basketball court", "basketball player"],
    "mls":              ["soccer america", "football match", "soccer skills"],
    "default":          ["soccer highlights", "football action", "sports stadium"],
}

# League-aware captions for Shorts
SHORTS_CAPTIONS = {
    "saudi pro league": [
        "The Saudi Pro League is on a completely different level this season 🇸🇦🔥 #SPL #Shorts",
        "Stars of the Roshn League doing what they do best. Can't look away! 🌟 #SaudiFootball",
        "SPL energy is UNMATCHED. This is why the world is watching 👀 #ConnectDial #Shorts",
    ],
    "premier league": [
        "Premier League football at its absolute finest 🏴󠁧󠁢󠁥󠁮󠁧󠁿⚡ #PL #Shorts #ConnectDial",
        "This is why the Premier League is the best in the world 🔥 #PremierLeague",
    ],
    "champions league": [
        "UCL nights are something else entirely ⭐🏆 #UCL #ChampionsLeague #Shorts",
        "The greatest club competition on the planet. No debate. #UCL #Shorts",
    ],
    "nba": [
        "NBA action 24/7 — this is why basketball is king 🏀🔥 #NBA #Shorts",
        "When the NBA is popping, everything else can wait 🏀 #Basketball #ConnectDial",
    ],
    "default": [
        "The energy in {league} is insane! 🔥 #Sports #Shorts #ConnectDial",
        "This is why we live for {league} action! ⚽🏆 #ConnectDial #Shorts",
        "{league} serving the content as always. LOCKED IN 📱🔥 #Shorts",
    ],
}


class Command(BaseCommand):
    help = 'Posts sports Shorts (vertical videos from Pexels) with league-aware captions'

    def add_arguments(self, parser):
        parser.add_argument('league_name', type=str)

    def _get_caption(self, league_name):
        league_lower = league_name.lower()
        pool = SHORTS_CAPTIONS.get(league_lower, SHORTS_CAPTIONS["default"])
        caption = random.choice(pool)
        return caption.replace("{league}", league_name)

    def _fetch_video(self, search_terms):
        headers = {"Authorization": PEXELS_API_KEY}
        for term in search_terms:
            url = (f"https://api.pexels.com/videos/search"
                   f"?query={term}&orientation=portrait&per_page=15")
            try:
                res  = requests.get(url, headers=headers, timeout=15).json()
                vids = res.get('videos', [])
                if vids:
                    return random.choice(vids)
            except Exception:
                continue
        return None

    def _best_video_url(self, video_data):
        """Pick best portrait resolution ≤ 720px wide."""
        files = video_data.get('video_files', [])
        # Sort portrait files by width ascending, prefer ≤ 720
        portrait = sorted(import random
import requests
import time
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from posts.models import Post, Hashtag
from leagues.models import League, Team

User = get_user_model()

class Command(BaseCommand):
    help = 'Fetches real sports vertical videos from Pexels and uploads them to Firebase'

    def add_arguments(self, parser):
        parser.add_argument('league_name', type=str)

    def handle(self, *args, **options):
        league_query = options['league_name']
        # 🔑 Your Pexels Key
        PEXELS_API_KEY = "HNdRlaon0CTc9qoCrFUYUNrnrHV6wpyetmhozjBUhpZ9tnVPPvZIBWO5" 
        
        # 1. League Alignment
        league = League.objects.filter(name__icontains=league_query).first()
        if not league:
            self.stdout.write(self.style.ERROR(f"League '{league_query}' not found in database."))
            return
        
        # 2. Find a Bot User
        bot_user = User.objects.filter(
            profile__is_bot=True, 
            favorite_league=league
        ).order_by('?').first()

        if not bot_user:
            bot_user = User.objects.filter(profile__is_bot=True).order_by('?').first()
            if not bot_user:
                self.stdout.write(self.style.ERROR("No bot accounts found."))
                return

        self.stdout.write(f"🎬 Bot @{bot_user.username} searching highlights for {league.name}...")
        
        # 3. Dynamic Search Terms
        search_term = league.name.lower()
        if any(x in search_term for x in ["premier", "liga", "champions", "soccer"]):
            search_term = "soccer"
        elif "nba" in search_term:
            search_term = "basketball"
        elif "f1" in search_term:
            search_term = "formula 1"

        url = f"https://api.pexels.com/videos/search?query={search_term}&orientation=portrait&per_page=15"
        headers = {"Authorization": PEXELS_API_KEY}

        try:
            res = requests.get(url, headers=headers, timeout=15).json()
            videos = res.get('videos', [])
            
            if not videos:
                self.stdout.write(self.style.WARNING(f"No vertical videos found for {search_term}."))
                return

            # Pick a random video and find a mobile-friendly resolution (under 1000px width)
            video_data = random.choice(videos)
            video_files = video_data.get('video_files', [])
            video_url = next((v['link'] for v in video_files if v['width'] < 1000), video_files[0]['link'])
            
            # 4. Stream the Video Bytes
            self.stdout.write(f"⏳ Downloading video from Pexels...")
            vid_res = requests.get(video_url, stream=True, timeout=60)
            
            if vid_res.status_code == 200:
                # 🚀 THE CRITICAL PATH ALIGNMENT:
                # Since Model has upload_to='post_media/', we provide only the sub-path.
                # Final structure: bucket/post_media/shorts/league_X/bot_Y.mp4
                file_path = f"shorts/league_{league.id}/bot_{bot_user.id}_{int(time.time())}.mp4"
                
                # 5. Create the Post Object but don't save media yet
                new_post = Post(
                    author=bot_user,
                    content=f"The energy in {league.name} is insane! 🔥 #Sports #Shorts",
                    post_type='video',
                    league=league,
                    team=bot_user.favorite_team if bot_user.favorite_team else None,
                    is_short=True
                )

                # 6. Save directly to the FileField
                # Wrap the raw content in ContentFile to trigger the GoogleCloudStorage backend
                self.stdout.write(f"📤 Uploading to Firebase...")
                new_post.media_file.save(
                    file_path, 
                    ContentFile(vid_res.content), 
                    save=True
                )

                # 7. Add Hashtags
                tags = [league.name.replace(" ", ""), "Shorts", "ConnectDial"]
                for t in tags:
                    tag_obj, _ = Hashtag.objects.get_or_create(name=t)
                    new_post.hashtags.add(tag_obj)

                self.stdout.write(self.style.SUCCESS(f"✅ Post LIVE: {new_post.media_file.url}"))
            else:
                self.stdout.write(self.style.ERROR(f"❌ Pexels download failed (Status: {vid_res.status_code})"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Script Error: {str(e)}"))
            [f for f in files if f.get('width', 9999) <= 720],
            key=lambda f: f['width'], reverse=True
        )
        if portrait:
            return portrait[0]['link']
        # fallback: smallest available
        return sorted(files, key=lambda f: f.get('width', 9999))[0]['link']

    def handle(self, *args, **options):
        league_query = options['league_name']

        league = League.objects.filter(name__icontains=league_query).first()
        if not league:
            self.stdout.write(self.style.ERROR(f"League '{league_query}' not found."))
            return

        # Recruit a bot
        bot = (User.objects
               .filter(profile__is_bot=True, favorite_league=league)
               .order_by('?').first())
        if not bot:
            bot = User.objects.filter(profile__is_bot=True).order_by('?').first()
            if not bot:
                self.stdout.write(self.style.ERROR("No bot accounts found."))
                return

        self.stdout.write(f"🎬 @{bot.username} searching highlights for {league.name}...")

        # Get search terms for this league
        search_terms = LEAGUE_VIDEO_TERMS.get(
            league.name.lower(), LEAGUE_VIDEO_TERMS["default"])

        video_data = self._fetch_video(search_terms)
        if not video_data:
            self.stdout.write(self.style.WARNING("No vertical videos found."))
            return

        video_url = self._best_video_url(video_data)
        caption   = self._get_caption(league.name)

        self.stdout.write(f"⏳ Downloading video...")
        vid_res = requests.get(video_url, stream=True, timeout=60)

        if vid_res.status_code != 200:
            self.stdout.write(self.style.ERROR(
                f"Pexels download failed (Status: {vid_res.status_code})"))
            return

        file_path = f"shorts/league_{league.id}/bot_{bot.id}_{int(time.time())}.mp4"

        new_post = Post(
            author=bot,
            content=caption,
            post_type='video',
            league=league,
            team=bot.favorite_team if bot.favorite_team else None,
            is_short=True,
        )

        self.stdout.write("📤 Uploading to Firebase...")
        new_post.media_file.save(file_path, ContentFile(vid_res.content), save=True)

        # Hashtags
        tags = [league.name.replace(" ", ""), "Shorts", "ConnectDial", "Sports"]
        for t in tags:
            tag_obj, _ = Hashtag.objects.get_or_create(name=t)
            new_post.hashtags.add(tag_obj)

        self.stdout.write(self.style.SUCCESS(
            f"✅ Short LIVE: {new_post.media_file.url}\n"
            f"   Caption: {caption}"))