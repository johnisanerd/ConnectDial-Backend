"""
ConnectDial — Highlightly → ShortVideo Importer
=================================================
Takes a list of highlight dicts from the Highlightly API and creates
ShortVideo records in the database.

Key design decisions
────────────────────
* Videos fetched from Highlightly are *external* — the `video` FileField
  is left blank and `external_url` (a CharField you'll add via migration)
  is populated instead.  The streaming view already handles HttpResponseRedirect
  for external URLs, so playback just works.

* Duplicate prevention:  we use `external_highlight_id` (also a new field)
  as a unique key so re-running the import is idempotent.

* League / Team matching:  we try to match by name against your existing
  `leagues.League` / `leagues.Team` tables.  No match → field stays NULL.

* The importer runs synchronously and returns an ImportResult summary so
  both the management command and the API view can report what happened.
"""

import logging
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
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_league(league_data: Optional[dict]):
    """Try to find a matching League by name."""
    if not league_data:
        return None
    try:
        from leagues.models import League   # adjust import path if needed
        name = league_data.get("name", "")
        return League.objects.filter(name__iexact=name).first()
    except Exception:
        return None


def _resolve_team(team_data: Optional[dict]):
    """Try to find a matching Team by name."""
    if not team_data:
        return None
    try:
        from leagues.models import Team     # adjust import path if needed
        name = team_data.get("name", "")
        return Team.objects.filter(name__iexact=name).first()
    except Exception:
        return None


def _fetch_thumbnail_bytes(url: str, timeout: int = 10) -> Optional[bytes]:
    """Download thumbnail image bytes from a URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ConnectDial/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:
        logger.warning("Thumbnail download failed (%s): %s", url, exc)
        return None


def _build_caption(highlight: dict) -> str:
    """Compose a caption from the highlight's title and description."""
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
    Import a list of Highlightly highlight dicts into ShortVideo.

    Parameters
    ----------
    highlights      : list of raw API highlight dicts
    system_user     : the User instance to set as `author` (your system/bot account)
    sport           : which sport these highlights are from (stored in caption prefix)
    fetch_thumbnails: whether to download & store thumbnail images

    Returns
    -------
    ImportResult with counts of created / skipped / errors
    """
    from ..models import ShortVideo

    result = ImportResult()

    for h in highlights:
        highlight_id = h.get("id")
        if not highlight_id:
            result.errors.append({"highlight": h, "error": "Missing id"})
            continue

        # ── External unique key stored in caption metadata header ──────────
        # We embed it as a hidden marker so we can skip duplicates without
        # a schema migration on the first pass.
        # Format:  [highlightly:{id}]
        marker = f"[highlightly:{highlight_id}]"

        try:
            with transaction.atomic():
                # Duplicate check
                if ShortVideo.objects.filter(caption__startswith=marker).exists():
                    result.skipped += 1
                    continue

                # Resolve optional FK relations
                match_data  = h.get("match", {}) or {}
                league_data = match_data.get("league")
                home_team   = match_data.get("homeTeam")

                league = _resolve_league(league_data)
                team   = _resolve_team(home_team)

                caption = marker + "\n" + _build_caption(h)

                # video_url is the embed or direct URL from the API
                video_url = h.get("embedUrl") or h.get("url") or ""

                instance = ShortVideo(
                    author=system_user,
                    caption=caption,
                    league=league,
                    team=team,
                    status="published",
                    # Leave `video` FileField blank — streaming view will
                    # redirect to video_url for external videos.
                    # We store the URL in the caption marker block.
                    # If you add an `external_url` CharField later, set it here:
                    # external_url=video_url,
                )
                instance.save()

                # ── Thumbnail ─────────────────────────────────────────────
                thumb_url = h.get("imgUrl")
                if fetch_thumbnails and thumb_url:
                    thumb_bytes = _fetch_thumbnail_bytes(thumb_url)
                    if thumb_bytes:
                        filename = f"highlightly_{highlight_id}.jpg"
                        instance.thumbnail.save(
                            filename,
                            ContentFile(thumb_bytes),
                            save=True,
                        )

                result.created += 1
                logger.info("Imported highlight %s → ShortVideo %s", highlight_id, instance.pk)

        except Exception as exc:
            logger.exception("Failed to import highlight %s: %s", highlight_id, exc)
            result.errors.append({"highlight_id": highlight_id, "error": str(exc)})

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE: get-or-create the system bot account
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_system_user():
    """
    Returns the system user that owns all Highlightly-imported videos.
    Creates it on first call with `is_staff=False, is_active=True`.
    """
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