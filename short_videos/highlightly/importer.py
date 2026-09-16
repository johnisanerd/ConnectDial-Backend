"""
ConnectDial — Highlightly → ShortVideo Importer
=================================================
Downloads highlight videos from Highlightly and uploads them to
Firebase Storage, storing the paths directly into Django model fields.
"""

import logging
import tempfile
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# RESULT CONTAINER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ImportResult:
    created:   int = 0
    skipped:   int = 0
    errors:    list = field(default_factory=list)

    @property
    def total_processed(self):
        return self.created + self.skipped + len(self.errors)

    def to_dict(self):
        return {
            "created":         self.created,
            "skipped":         self.skipped,
            "errors":          self.errors,
            "total_processed": self.total_processed,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE FIREBASE/GCS STORAGE
# ─────────────────────────────────────────────────────────────────────────────

def _save_to_media_storage(local_path: str, destination_blob: str) -> str:
    """Store a downloaded file through Django's Firebase media backend.

    The deterministic key is returned and stored in the model field; no public
    Firebase URL or public ACL is created. Existing orphaned objects from a
    previously interrupted import are reused safely.
    """
    if default_storage.exists(destination_blob):
        return destination_blob

    with open(local_path, "rb") as source:
        saved_name = default_storage.save(destination_blob, File(source))
    return saved_name


def _upload_to_firebase(local_path: str, destination_blob: str) -> str:
    return _save_to_media_storage(local_path, destination_blob)


def _upload_thumbnail_to_firebase(local_path: str, destination_blob: str) -> str:
    return _save_to_media_storage(local_path, destination_blob)


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_DOWNLOADABLE_SOURCES = ("streamable", "oddsjam", "scorebat", "dailymotion")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _is_downloadable_url(url: str) -> bool:
    """Return True if the URL points to a directly downloadable video."""
    if not url:
        return False
    skip = ("youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com")
    return not any(s in url for s in skip)


def _download_video(url: str, timeout: int = 60) -> Optional[str]:
    """Download a video URL to a temp file."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                tmp_path = tmp.name
                chunk_size = 1024 * 512  # 512 KB
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
    """Download thumbnail to a temp file. Returns path or None."""
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
# FK RESOLVERS
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
    """
    Import a large batch of Highlightly highlights into ShortVideo.

    Optimized for high volume:
      1. Prefetches existing markers using fast SQL list filtering.
      2. Runs external network transactions outside atomic SQL save cycles.
      3. Implements strict top-of-loop scope sanitization to prevent UnboundLocalErrors.
    """
    from ..models import ShortVideo

    result = ImportResult()
    if not highlights:
        return result

    # ── High-Volume Optimization: Prefetch Existing Records ──────────────────
    valid_highlights = []
    for h in highlights:
        h_id = h.get("id")
        if h_id:
            valid_highlights.append(h)
        else:
            result.errors.append({"highlight": h, "error": "Missing id"})

    if not valid_highlights:
        return result

    # Fast SQL exact match lookup array construction
    expected_markers = [f"[highlightly:{h.get('id')}]" for h in valid_highlights]

    # Bulk query to eliminate N+1 latency blocks
    existing_captions = set(
        ShortVideo.objects.filter(
            caption__in=expected_markers
        ).values_list("caption", flat=True)
    )

    # ── Core Iteration Loop ──────────────────────────────────────────────────
    for h in valid_highlights:
        highlight_id = h.get("id")
        marker = f"[highlightly:{highlight_id}]"

        # Bulk duplicate lookup execution check
        if marker in existing_captions:
            result.skipped += 1
            continue

        video_url = h.get("url") or h.get("embedUrl") or ""
        source = h.get("source", "").lower()

        tmp_video_path = None
        tmp_thumb_path = None

        # ✅ Scope Sanitization: Variables are reset to blank strings every single loop
        firebase_video_key = ""
        firebase_thumb_key = ""

        try:
            # ── 1. Pipeline Stage A: Run Network Calls OUTSIDE DB Transactions ──
            if _is_downloadable_url(video_url):
                logger.info("Downloading highlight content [%s]...", highlight_id)
                tmp_video_path = _download_video(video_url)

                if tmp_video_path:
                    firebase_video_blob = f"shorts/highlights/{highlight_id}.mp4"
                    try:
                        firebase_video_key = _upload_to_firebase(tmp_video_path, firebase_video_blob)
                    except Exception as fb_exc:
                        logger.warning("Firebase video push dropped for %s: %s", highlight_id, fb_exc)

            if fetch_thumbnails and h.get("imgUrl"):
                tmp_thumb_path = _download_thumbnail(h.get("imgUrl"))
                if tmp_thumb_path:
                    firebase_thumb_blob = f"shorts/highlights/thumbs/{highlight_id}.jpg"
                    try:
                        firebase_thumb_key = _upload_thumbnail_to_firebase(tmp_thumb_path, firebase_thumb_blob)
                    except Exception as fb_exc:
                        logger.warning("Firebase thumbnail push dropped for %s: %s", highlight_id, fb_exc)

            # ── 2. Pipeline Stage B: Fast Database Persistence ─────────────────
            with transaction.atomic():
                # Real-time defensive check inside the transaction row isolation container
                if ShortVideo.objects.filter(caption__startswith=marker).exists():
                    result.skipped += 1
                    continue

                match_data = h.get("match", {}) or {}
                league = _resolve_league(match_data.get("league"))
                team = _resolve_team(match_data.get("homeTeam"))
                caption = marker + "\n" + _build_caption(h)

                if not firebase_video_key and video_url:
                    caption += f"\nexternal_url:{video_url}"

                instance = ShortVideo(
                    author=system_user,
                    caption=caption,
                    league=league,
                    team=team,
                    status="published",
                )

                # ✅ Explicit Field Mapping: Assigning direct path strings back to file fields
                if firebase_video_key:
                    instance.video = firebase_video_key

                if firebase_thumb_key:
                    instance.thumbnail = firebase_thumb_key
                else:
                    # Disk fallback routine if bucket stream was bypassed or dropped
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
            logger.exception("Failed processing record row execution %s: %s", highlight_id, exc)
            result.errors.append({"highlight_id": highlight_id, "error": str(exc)})

        finally:
            # Clean local temp scratch files completely
            for path in (tmp_video_path, tmp_thumb_path):
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass

    return result


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM USER
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_system_user():
    """Returns the bot user that owns all Highlightly-imported videos."""
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
        logger.info("Created system user '%s'", username)
    return user