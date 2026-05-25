"""
ConnectDial — Highlightly → ShortVideo Importer
=================================================
Downloads highlight videos from Highlightly and uploads them to
Firebase Storage, storing the public Firebase URL in ShortVideo.video
(as a URLField-compatible path) so the app streams from your own bucket.
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
# FIREBASE UPLOAD
# ─────────────────────────────────────────────────────────────────────────────

def _upload_to_firebase(local_path: str, destination_blob: str) -> str:
    """
    Upload a local file to Firebase Storage and return its public URL.

    Uses the firebase_admin SDK which is already initialised by your
    server startup (the '✅ Firebase Admin SDK initialized' message).

    Parameters
    ----------
    local_path       : absolute path to the file on disk
    destination_blob : path inside the bucket, e.g. 'shorts/highlights/xyz.mp4'

    Returns
    -------
    Public HTTPS URL of the uploaded file.
    """
    import firebase_admin
    from firebase_admin import storage

    bucket = storage.bucket()
    blob = bucket.blob(destination_blob)
    blob.upload_from_filename(local_path, content_type="video/mp4")

    # Make the file publicly readable
    blob.make_public()

    return blob.public_url


def _upload_thumbnail_to_firebase(local_path: str, destination_blob: str) -> str:
    """Upload a thumbnail image to Firebase Storage and return its public URL."""
    import firebase_admin
    from firebase_admin import storage

    bucket = storage.bucket()
    blob = bucket.blob(destination_blob)
    blob.upload_from_filename(local_path, content_type="image/jpeg")
    blob.make_public()
    return blob.public_url


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# These are direct-downloadable video sources we know how to handle.
# YouTube embed URLs cannot be downloaded directly — we skip those.
_DOWNLOADABLE_SOURCES = ("streamable", "oddsjam", "scorebat", "dailymotion")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _is_downloadable_url(url: str) -> bool:
    """Return True if the URL points to a directly downloadable video."""
    if not url:
        return False
    # Skip YouTube/embed-only sources
    skip = ("youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com")
    return not any(s in url for s in skip)


def _download_video(url: str, timeout: int = 120) -> Optional[str]:
    """
    Download a video URL to a temp file.
    Returns the temp file path, or None on failure.
    Caller is responsible for deleting the file.
    """
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            suffix = ".mp4"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
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
    Import Highlightly highlights into ShortVideo.

    For each highlight:
      1. Download the video file to a temp file
      2. Upload to Firebase Storage → get public URL
      3. Save ShortVideo with firebase_url stored in caption metadata
         (video FileField stores the Firebase path)
      4. Download + upload thumbnail the same way
    """
    from ..models import ShortVideo

    result = ImportResult()

    for h in highlights:
        highlight_id = h.get("id")
        if not highlight_id:
            result.errors.append({"highlight": h, "error": "Missing id"})
            continue

        marker = f"[highlightly:{highlight_id}]"

        # Determine best video URL to download
        video_url = h.get("url") or h.get("embedUrl") or ""
        source    = h.get("source", "").lower()

        tmp_video_path = None
        tmp_thumb_path = None

        try:
            with transaction.atomic():
                # ── Duplicate check ───────────────────────────────────────
                if ShortVideo.objects.filter(caption__startswith=marker).exists():
                    result.skipped += 1
                    continue

                # ── Resolve FKs ───────────────────────────────────────────
                match_data  = h.get("match", {}) or {}
                league      = _resolve_league(match_data.get("league"))
                team        = _resolve_team(match_data.get("homeTeam"))
                caption     = marker + "\n" + _build_caption(h)

                # ── Download + upload video ───────────────────────────────
                firebase_video_url = ""

                if _is_downloadable_url(video_url):
                    logger.info("Downloading video for highlight %s from %s", highlight_id, video_url)
                    tmp_video_path = _download_video(video_url)

                    if tmp_video_path:
                        firebase_blob = f"shorts/highlights/{highlight_id}.mp4"
                        try:
                            firebase_video_url = _upload_to_firebase(tmp_video_path, firebase_blob)
                            logger.info("Uploaded to Firebase: %s", firebase_video_url)
                        except Exception as fb_exc:
                            logger.warning("Firebase upload failed for %s: %s", highlight_id, fb_exc)
                    else:
                        logger.warning("Could not download video for highlight %s", highlight_id)
                else:
                    logger.info(
                        "Skipping download for highlight %s — source '%s' not directly downloadable",
                        highlight_id, source
                    )

                # Store Firebase URL in caption so serializer can return it
                # until you add a proper external_url field via migration
                if firebase_video_url:
                    caption += f"\nfirebase_url:{firebase_video_url}"
                elif video_url:
                    # Fallback: store original URL so video isn't completely broken
                    caption += f"\nexternal_url:{video_url}"

                instance = ShortVideo(
                    author=system_user,
                    caption=caption,
                    league=league,
                    team=team,
                    status="published",
                )
                instance.save()

                # ── Download + upload thumbnail ───────────────────────────
                thumb_url = h.get("imgUrl")
                if fetch_thumbnails and thumb_url:
                    tmp_thumb_path = _download_thumbnail(thumb_url)
                    if tmp_thumb_path:
                        firebase_thumb_blob = f"shorts/highlights/thumbs/{highlight_id}.jpg"
                        try:
                            firebase_thumb_url = _upload_thumbnail_to_firebase(
                                tmp_thumb_path, firebase_thumb_blob
                            )
                            # Save thumbnail URL — store as ContentFile with the Firebase URL
                            # so Django's ImageField name holds the blob path
                            instance.thumbnail.name = firebase_thumb_blob
                            instance.save(update_fields=["thumbnail"])
                            logger.info("Thumbnail uploaded: %s", firebase_thumb_url)
                        except Exception as thumb_exc:
                            logger.warning("Thumbnail Firebase upload failed: %s", thumb_exc)
                            # Fallback: download bytes and save via Django storage
                            try:
                                with open(tmp_thumb_path, "rb") as f:
                                    instance.thumbnail.save(
                                        f"highlightly_{highlight_id}.jpg",
                                        ContentFile(f.read()),
                                        save=True,
                                    )
                            except Exception:
                                pass

                result.created += 1
                logger.info("Imported highlight %s → ShortVideo %s", highlight_id, instance.pk)

        except Exception as exc:
            logger.exception("Failed to import highlight %s: %s", highlight_id, exc)
            result.errors.append({"highlight_id": highlight_id, "error": str(exc)})

        finally:
            # Always clean up temp files
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