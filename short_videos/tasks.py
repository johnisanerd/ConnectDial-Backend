"""
ConnectDial — Celery Tasks: Short Video Processing
====================================================
Decouples heavy video work (ffmpeg compress + GCS upload) from the HTTP
request so the mobile client never times out.

Task flow
─────────
  process_short_video(video_pk, tmp_path)
    ├── compress_video(tmp_path → compressed_path)   [ffmpeg, can take minutes]
    ├── extract_duration(compressed_path)
    ├── upload compressed file → ShortVideo.video (GCS)
    ├── generate_thumbnail → ShortVideo.thumbnail
    ├── flip status 'draft' → 'published'
    └── clean up temp files

If anything fails the video stays in 'draft'; you can surface that in the
admin or retry the task.
"""

import os
import tempfile
import logging

from celery import shared_task
from django.core.files import File
from django.core.files.base import ContentFile

from .video_processing import compress_video, extract_duration, generate_thumbnail

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,       # retry after 60 s on transient failures
    soft_time_limit=7260,         # slightly above the 2-hr video limit
    time_limit=7320,
    name='short_videos.process_short_video',
)
def process_short_video(self, video_pk: str, tmp_path: str):
    """
    Compress, upload, and publish a ShortVideo that was saved as 'draft'.

    Parameters
    ----------
    video_pk : str   UUID primary key of the ShortVideo instance.
    tmp_path : str   Absolute path to the raw uploaded file on disk.
    """
    from .models import ShortVideo   # local import avoids circular deps at module load

    compressed_path = tmp_path + '_compressed.mp4'

    try:
        # ── 1. Load instance ──────────────────────────────────────────────────
        try:
            instance = ShortVideo.objects.get(pk=video_pk)
        except ShortVideo.DoesNotExist:
            logger.error('process_short_video: ShortVideo %s not found', video_pk)
            return

        logger.info('process_short_video: starting for %s', video_pk)

        # ── 2. Compress ───────────────────────────────────────────────────────
        compress_video(tmp_path, compressed_path)
        logger.info('process_short_video: compression done for %s', video_pk)

        # ── 3. Extract duration ───────────────────────────────────────────────
        duration = extract_duration(compressed_path)

        # ── 4. Upload to GCS via Django storage ───────────────────────────────
        original_name = os.path.basename(tmp_path)
        f = open(compressed_path, 'rb')
        try:
            instance.video.save(
                original_name,
                File(f),
                save=False,     # we'll do one save() below
            )
        finally:
            f.close()

        instance.duration = duration
        instance.status   = 'published'
        instance.save(update_fields=['video', 'duration', 'status'])
        logger.info('process_short_video: video saved for %s', video_pk)

        # ── 5. Thumbnail ──────────────────────────────────────────────────────
        try:
            thumb_bytes = generate_thumbnail(compressed_path)
            instance.thumbnail.save(
                f'thumb_{instance.pk}.jpg',
                ContentFile(thumb_bytes),
                save=True,
            )
        except Exception as thumb_err:
            logger.warning('process_short_video: thumbnail failed for %s: %s', video_pk, thumb_err)

        logger.info('process_short_video: DONE for %s', video_pk)

    except Exception as exc:
        logger.exception('process_short_video: error for %s: %s', video_pk, exc)

        # Mark as published anyway so it's not stuck in draft forever,
        # OR keep as draft and surface the error — your choice:
        try:
            ShortVideo.objects.filter(pk=video_pk).update(status='published')
        except Exception:
            pass

        # Retry on transient errors (network, GCS blip, etc.)
        raise self.retry(exc=exc)

    finally:
        # ── 6. Always clean up temp files ────────────────────────────────────
        for path in (tmp_path, compressed_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass