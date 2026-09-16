from celery import shared_task
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import ShortVideo
from .video_processing import (
    compress_video,
    extract_duration,
    generate_thumbnail,
)

import tempfile
import shutil
import os
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=7260,
    time_limit=7320,
    name='short_videos.process_short_video',
)
def process_short_video(self, video_pk):
    compressed_path = None
    temp_input_path = None
    instance = None

    try:
        instance = ShortVideo.objects.get(pk=video_pk)

        if not instance.video:
            logger.error("No video attached for %s", video_pk)
            return

        logger.info("Processing started for %s", video_pk)
        instance.status = 'processing'
        instance.save(update_fields=['status'])

        # Copy remote/local storage object to a temporary file. This works for
        # MinIO/S3 and avoids FieldFile.path, which only exists on local disk.
        suffix = os.path.splitext(instance.video.name)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_input:
            temp_input_path = temp_input.name
            with instance.video.open("rb") as src:
                shutil.copyfileobj(src, temp_input, length=1024 * 1024)

        compressed_path = temp_input_path + "_compressed.mp4"
        compress_video(temp_input_path, compressed_path)
        logger.info("Compression done for %s", video_pk)

        instance.duration = extract_duration(compressed_path)
        old_video_name = instance.video.name

        # Stream the processed file back to storage instead of reading the
        # entire video into RAM with ContentFile(f.read()).
        with open(compressed_path, "rb") as processed_file:
            instance.video.save(
                os.path.basename(old_video_name),
                File(processed_file),
                save=False,
            )

        try:
            thumb_bytes = generate_thumbnail(compressed_path)
            instance.thumbnail.save(
                f"thumb_{instance.pk}.jpg",
                ContentFile(thumb_bytes),
                save=False,
            )
        except Exception as thumb_err:
            logger.warning("Thumbnail failed for %s: %s", video_pk, thumb_err)

        instance.status = "published"
        instance.save()

        # Remove the original upload if processing stored the final video under
        # a different object key. Avoid leaving large orphaned MinIO objects.
        if old_video_name and old_video_name != instance.video.name:
            try:
                default_storage.delete(old_video_name)
            except Exception as delete_err:
                logger.warning("Could not delete original %s: %s", old_video_name, delete_err)

        logger.info("Processing completed for %s", video_pk)

    except Exception as exc:
        logger.exception("Processing failed for %s: %s", video_pk, exc)

        if instance is not None:
            try:
                instance.status = "failed"
                instance.save(update_fields=["status"])
            except Exception:
                pass

        raise self.retry(exc=exc)

    finally:
        for path in [temp_input_path, compressed_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass
