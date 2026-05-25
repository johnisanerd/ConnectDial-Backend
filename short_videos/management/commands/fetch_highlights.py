"""
ConnectDial — Highlightly → ShortVideo Importer
=================================================
Optimized high-volume video importer engine.
"""

import logging
import tempfile
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()


@dataclass
class ImportResult:
    created:   int = 0
    skipped:   int = 0
    errors:    list = field(default_factory=list)

    @property
    def total_processed(self):
        return self.created + self.skipped + len(self.errors)


# ─────────────────────────────────────────────────────────────────────────────
# FIREBASE UPLOAD (Optimized: No slow programmatic ACL calls)
# ─────────────────────────────────────────────────────────────────────────────

def _upload_to_firebase(local_path: str, destination_blob: str) -> str:
    """Upload a local file to Firebase Storage and return its public URL."""
    import firebase_admin
    from firebase_admin import storage
    from django.conf import settings

    bucket_name = getattr(settings, "GS_BUCKET_NAME", "connect-c894b.firebasestorage.app")
    bucket = storage.bucket(bucket_name)
    blob = bucket.blob(destination_blob)

    blob.upload_from_filename(local_path, content_type="video/mp4")
    return blob.public_url


def _upload_thumbnail_to_firebase(local_path: str, destination_blob: str) -> str:
    """Upload a thumbnail image to Firebase Storage and return its public URL."""
    import firebase_admin
    from firebase_admin import storage
    from django.conf import settings

    bucket_name = getattr(settings, "GS_BUCKET_NAME", "connect-c894b.firebasestorage.app")
    bucket = storage.bucket(bucket_name)
    blob = bucket.blob(destination_blob)

    blob.upload_from_filename(local_path, content_type="image/jpeg")
    return blob.public_url


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD HELPERS (Optimized with custom headers)
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _is_downloadable_url(url: str) -> bool:
    if not url:
        return False
    skip = ("youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com")
    return not any(s in url for s in skip)


def _download_video(url: str, timeout: int = 60) -> Optional[str]:
    """Download a video URL to a temporary local file scratchpad."""
    try:
        # Pass headers explicitly to bypass Reddit/v.redd.it 403 barriers
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                tmp_path = tmp.name
                chunk_size = 1024 * 512
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    tmp.write(chunk)
        return tmp_path
    except Exception as exc:
        logger.warning("Video download failed (%s): %s", url, exc)
        return None


def _download_thumbnail(url: str, timeout: int = 15) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(resp.read())
                return tmp.name
    except Exception as exc:
        logger.warning("Thumbnail download failed (%s): %s", url, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVERS
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_league(league_data: Optional[dict]):
    if not league_data:
        return None
    try:
        from leagues.models import League
        return League.objects.filter(name__iexact=league_data.get("name", "")).first()
    except Exception:
        return None


def _resolve_team(team_data: Optional[dict]):
    if not team_data:
        return None
    try:
        from leagues.models import Team
        return Team.objects.filter(name__iexact=team_data.get("name", "")).first()
    except Exception:
        return None


def _build_caption(highlight: dict) -> str:
    parts = [highlight.get("title", "")]
    desc = highlight.get("description", "")
    if desc and desc.lower() != parts[0].lower():
        parts.append(desc)
    return "\n".join(p for p in parts if p).strip()[:2200]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN IMPORTER
# ─────────────────────────────────────────────────────────────────────────────

def import_highlights(
    highlights: list[dict],
    *,
    system_user,
    sport: str = "football",
    fetch_thumbnails: bool = True,
) -> ImportResult:
    from ..models import ShortVideo

    result = ImportResult()
    if not highlights:
        return result

    valid_highlights = [h for h in highlights if h.get("id")]
    if not valid_highlights:
        return result

    # Bulk duplicate isolation optimization
    existing_captions = set(
        ShortVideo.objects.filter(
            caption__regex=r"^\[highlightly:(" + "|".join(str(h.get('id')) for h in valid_highlights) + r")\]"
        ).values_list("caption", flat=True)
    )

    for h in valid_highlights:
        highlight_id = h.get("id")
        marker = f"[highlightly:{highlight_id}]"

        if any(cap.startswith(marker) for cap in existing_captions):
            result.skipped += 1
            continue

        video_url = h.get("url") or h.get("embedUrl") or ""
        source = h.get("source", "").lower()

        tmp_video_path = None
        tmp_thumb_path = None
        firebase_video_url = ""
        firebase_thumb_url = ""

        try:
            # ── 1. Pipeline Stage A: Run Network Calls OUTSIDE DB Transactions ──
            if _is_downloadable_url(video_url):
                logger.info("Downloading highlight content [%s]...", highlight_id)
                tmp_video_path = _download_video(video_url)

                if tmp_video_path:
                    firebase_video_blob = f"shorts/highlights/{highlight_id}.mp4"
                    try:
                        firebase_video_url = _upload_to_firebase(tmp_video_path, firebase_video_blob)
                    except Exception as fb_exc:
                        logger.warning("Firebase video push dropped for %s: %s", highlight_id, fb_exc)

            if fetch_thumbnails and h.get("imgUrl"):
                tmp_thumb_path = _download_thumbnail(h.get("imgUrl"))
                if tmp_thumb_path:
                    firebase_thumb_blob = f"shorts/highlights/thumbs/{highlight_id}.jpg"
                    try:
                        firebase_thumb_url = _upload_thumbnail_to_firebase(tmp_thumb_path, firebase_thumb_blob)
                    except Exception as fb_exc:
                        logger.warning("Firebase thumbnail push dropped for %s: %s", highlight_id, fb_exc)

            # ── 2. Pipeline Stage B: Fast Database Persistence ──
            with transaction.atomic():
                match_data = h.get("match", {}) or {}
                league = _resolve_league(match_data.get("league"))
                team = _resolve_team(match_data.get("homeTeam"))
                caption = marker + "\n" + _build_caption(h)

                if firebase_video_url:
                    caption += f"\nfirebase_url:{firebase_video_url}"
                elif video_url:
                    caption += f"\nexternal_url:{video_url}"

                instance = ShortVideo(
                    author=system_user,
                    caption=caption,
                    league=league,
                    team=team,
                    status="published",
                )

                # Set file fields using paths matching our default storage layout
                if firebase_video_url:
                    instance.video.name = f"shorts/highlights/{highlight_id}.mp4"
                if firebase_thumb_url:
                    instance.thumbnail.name = f"shorts/highlights/thumbs/{highlight_id}.jpg"
                else:
                    # Secondary internal disk fallback fallback option if Firebase dropped
                    if tmp_thumb_path:
                        with open(tmp_thumb_path, "rb") as f:
                            instance.thumbnail.save(
                                f"highlightly_{highlight_id}.jpg",
                                ContentFile(f.read()),
                                save=False,
                            )

                instance.save()
                result.created += 1
                logger.info("Successfully indexed highlight %s", highlight_id)

        except Exception as exc:
            logger.exception("Error processing highlight record row %s: %s", highlight_id, exc)
            result.errors.append({"highlight_id": highlight_id, "error": str(exc)})

        finally:
            for path in (tmp_video_path, tmp_thumb_path):
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass

    return result


def get_or_create_system_user():
    username = "highlightly_bot"
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": "bot@connectdial.internal",
            "is_staff": False,
            "is_active": True,
        },
    )
    if created:
        user.set_unusable_password()
        user.save()
    return user